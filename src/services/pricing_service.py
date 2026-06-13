"""
Pricing Service — AlphaVantage integration for REIT price data.

Fetches daily/weekly prices for individual REITs and REIT ETFs,
computes returns, moving averages, and volatility metrics.

Rate limit: 25 requests/day (AlphaVantage free tier).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import boto3
import requests

from cubiczan_resilience import resilient

logger = logging.getLogger(__name__)

ALPHAVANTAGE_BASE = "https://www.alphavantage.co/query"

# REIT ETFs
REIT_ETFS: Dict[str, str] = {
    "VNQ": "Vanguard Real Estate ETF",
    "SCHH": "Schwab U.S. REIT ETF",
    "IYR": "iShares U.S. Real Estate ETF",
    "XLRE": "Real Estate Select Sector SPDR",
}


class PricingService:
    """Service for fetching REIT and ETF price data from AlphaVantage."""

    def __init__(
        self,
        api_key: str = "",
        rate_limiter: Optional[Any] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ALPHA_VANTAGE_KEY", "")
        self._session = requests.Session()
        self._daily_limit: int = 25
        self._rate_limiter = rate_limiter
        # Process-local fast-path counter. Authoritative budget lives in SSM
        # (see _get_call_count); this is a same-container short-circuit.
        self._call_count: int = 0
        # The AlphaVantage daily-call counter is persisted in SSM Parameter
        # Store so the 25/day free-tier budget survives Lambda cold starts
        # (a process-local counter resets to 0 on every new container). The
        # SSM parameter name is keyed by UTC date so it self-rolls each day.
        self._ssm_prefix = os.environ.get(
            "ALPHAVANTAGE_COUNTER_PREFIX", "/scope-sentinel/alphavantage/calls"
        )
        self._ssm = None

    def _counter_param_name(self) -> str:
        from datetime import datetime
        return f"{self._ssm_prefix}/{datetime.utcnow().strftime('%Y-%m-%d')}"

    def _ssm_client(self):
        if self._ssm is None:
            self._ssm = boto3.client("ssm")
        return self._ssm

    def _get_call_count(self) -> int:
        """Read today's AlphaVantage call count from SSM (0 if unset/unavailable)."""
        try:
            resp = self._ssm_client().get_parameter(Name=self._counter_param_name())
            return int(resp["Parameter"]["Value"])
        except Exception as e:
            # Missing parameter (first call of the day) or transient SSM error:
            # treat as 0 calls so we fail open rather than blocking ingestion.
            logger.debug(f"AlphaVantage counter read failed (treating as 0): {e}")
            return 0

    def _increment_call_count(self, current: int) -> None:
        """Persist the incremented call count back to SSM."""
        try:
            self._ssm_client().put_parameter(
                Name=self._counter_param_name(),
                Value=str(current + 1),
                Type="String",
                Overwrite=True,
            )
        except Exception as e:
            logger.warning(f"AlphaVantage counter write failed: {e}")

    @resilient(timeout=30, max_attempts=3)
    def _request(self, params: Dict) -> Dict:
        """Issue the HTTP request to AlphaVantage with retry/backoff/jitter.

        Raises on transport/HTTP errors so @resilient can retry transient
        failures; the public _get wrapper converts a final failure to None.
        """
        response = self._session.get(ALPHAVANTAGE_BASE, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _get(self, params: Dict) -> Optional[Dict]:
        """Make a throttled request to AlphaVantage."""
        # Authoritative count is the max of the SSM-persisted (cold-start
        # durable) value and this container's local counter.
        call_count = max(self._get_call_count(), self._call_count)
        if call_count >= self._daily_limit:
            logger.warning("AlphaVantage daily limit reached")
            return None

        params["apikey"] = self.api_key
        params["datatype"] = "json"
        try:
            data = self._request(params)
            self._call_count += 1
            self._increment_call_count(call_count)
            if "Error Message" in data:
                logger.error(f"AlphaVantage error: {data['Error Message']}")
                return None
            if "Note" in data:
                logger.warning(f"AlphaVantage rate limit note: {data['Note']}")
                return None
            return data
        except requests.RequestException as e:
            logger.error(f"AlphaVantage request failed: {e}")
            return None

    def get_daily_prices(self, ticker: str, output_size: str = "compact") -> Optional[List[Dict]]:
        """Get daily price data for a ticker. output_size: compact (100 days) or full (20+ years)."""
        data = self._get({
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "outputsize": output_size,
        })
        if not data or "Time Series (Daily)" not in data:
            return None

        series = data["Time Series (Daily)"]
        prices = []
        for date_str, values in sorted(series.items(), reverse=True):
            prices.append({
                "date": date_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            })
        return prices

    def get_weekly_prices(self, ticker: str) -> Optional[List[Dict]]:
        """Get weekly price data for a ticker."""
        data = self._get({
            "function": "TIME_SERIES_WEEKLY",
            "symbol": ticker,
        })
        if not data or "Weekly Time Series" not in data:
            return None

        series = data["Weekly Time Series"]
        prices = []
        for date_str, values in sorted(series.items(), reverse=True):
            prices.append({
                "date": date_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            })
        return prices

    @staticmethod
    def compute_returns(prices: List[Dict], periods: List[int] = None) -> Dict[str, float]:
        """Compute price returns for multiple periods."""
        if periods is None:
            periods = [21, 63, 126, 252]  # ~1mo, 3mo, 6mo, 1yr (trading days)
        if not prices or len(prices) < 2:
            return {}

        results: Dict[str, float] = {}
        current_price = prices[0]["close"]

        labels = {21: "1m", 63: "3m", 126: "6m", 252: "1y"}
        for period in periods:
            if len(prices) > period:
                past_price = prices[period]["close"]
                ret = (current_price - past_price) / past_price
                label = labels.get(period, f"{period}d")
                results[f"return_{label}"] = round(ret * 100, 2)

        return results

    @staticmethod
    def compute_moving_averages(prices: List[Dict], windows: List[int] = None) -> Dict[str, Optional[float]]:
        """Compute simple moving averages."""
        if windows is None:
            windows = [20, 50, 200]
        if not prices:
            return {}

        results: Dict[str, Optional[float]] = {}
        for window in windows:
            if len(prices) >= window:
                ma = sum(p["close"] for p in prices[:window]) / window
                results[f"ma_{window}"] = round(ma, 2)
                # Distance from current price
                results[f"pct_from_ma_{window}"] = round(
                    ((prices[0]["close"] - ma) / ma) * 100, 2
                )
            else:
                results[f"ma_{window}"] = None
                results[f"pct_from_ma_{window}"] = None

        return results

    @staticmethod
    def compute_volatility(prices: List[Dict], window: int = 20) -> Dict[str, float]:
        """Compute price volatility (annualized std dev of daily returns)."""
        if not prices or len(prices) < window + 1:
            return {"volatility_annual": 0.0, "volatility_daily": 0.0}

        daily_returns = []
        for i in range(len(prices) - 1):
            ret = (prices[i]["close"] - prices[i + 1]["close"]) / prices[i + 1]["close"]
            daily_returns.append(ret)

        # Rolling window
        recent = daily_returns[:window]
        avg = sum(recent) / len(recent)
        variance = sum((r - avg) ** 2 for r in recent) / len(recent)
        daily_vol = variance ** 0.5
        annual_vol = daily_vol * (252 ** 0.5)

        return {
            "volatility_daily": round(daily_vol * 100, 4),
            "volatility_annual": round(annual_vol * 100, 2),
        }

    def get_reit_summary(self, ticker: str) -> Dict[str, Any]:
        """Get comprehensive price summary for a REIT or ETF."""
        prices = self.get_daily_prices(ticker, output_size="compact")
        if not prices:
            return {"ticker": ticker, "error": "No price data available"}

        returns = self.compute_returns(prices)
        mas = self.compute_moving_averages(prices)
        vol = self.compute_volatility(prices)

        current = prices[0]
        return {
            "ticker": ticker,
            "price": current["close"],
            "date": current["date"],
            "volume": current["volume"],
            "returns_pct": returns,
            "moving_averages": mas,
            "volatility": vol,
        }

    def get_etf_summary(self, etf_ticker: str = "VNQ") -> Dict[str, Any]:
        """Get price summary for a REIT ETF."""
        if etf_ticker not in REIT_ETFS:
            logger.warning(f"Unknown ETF: {etf_ticker}")
        return self.get_reit_summary(etf_ticker)

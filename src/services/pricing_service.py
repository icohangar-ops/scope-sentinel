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

import requests

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
        self._call_count: int = 0
        self._daily_limit: int = 25
        self._rate_limiter = rate_limiter

    def _get(self, params: Dict) -> Optional[Dict]:
        """Make a throttled request to AlphaVantage."""
        if self._call_count >= self._daily_limit:
            logger.warning("AlphaVantage daily limit reached")
            return None

        params["apikey"] = self.api_key
        params["datatype"] = "json"
        try:
            response = self._session.get(ALPHAVANTAGE_BASE, params=params, timeout=30)
            response.raise_for_status()
            self._call_count += 1
            data = response.json()
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

"""
FRED Service — Federal Reserve Economic Data integration.

Fetches macro-economic indicators from the FRED API that are relevant
to REIT analysis: interest rates, CPI, housing indices, construction, etc.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.models.market_indicator import FREDIndicator, MarketIndicator

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred"


class FREDService:
    """Service for fetching macro-economic data from FRED API."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key or os.environ.get("FRED_API_KEY", "")
        self._session = requests.Session()

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a request to FRED API."""
        params = params or {}
        params["api_key"] = self.api_key
        params["file_type"] = "json"
        try:
            response = self._session.get(f"{FRED_BASE_URL}{endpoint}", params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"FRED request failed: {e}")
            return None

    def get_series(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        sort_order: str = "desc",
    ) -> List[MarketIndicator]:
        """Fetch a FRED time series and return as MarketIndicator objects."""
        params: Dict[str, Any] = {
            "series_id": series_id,
            "limit": limit,
            "sort_order": sort_order,
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date

        data = self._get("/series/observations", params)
        if not data or "observations" not in data:
            return []

        indicators = []
        for obs in data["observations"]:
            try:
                value = float(obs["value"])
                if value == 0.0 and obs["value"] == ".":
                    continue  # Skip missing values
                indicator = MarketIndicator.from_fred_response(
                    series_id=series_id,
                    date=obs["date"],
                    value=value,
                )
                indicators.append(indicator)
            except (ValueError, TypeError):
                continue

        return indicators

    def get_latest_value(self, series_id: str) -> Optional[float]:
        """Get the most recent value for a series."""
        indicators = self.get_series(series_id, limit=1)
        return indicators[0].value if indicators else None

    def get_spread(self, series_id_1: str, series_id_2: str) -> Optional[float]:
        """Get the spread between two series (latest values)."""
        v1 = self.get_latest_value(series_id_1)
        v2 = self.get_latest_value(series_id_2)
        if v1 is not None and v2 is not None:
            return round(v1 - v2, 4)
        return None

    def get_reit_relevant_data(self, lookback_months: int = 24) -> Dict[str, List[MarketIndicator]]:
        """Fetch all REIT-relevant FRED indicators."""
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_months * 30)).strftime("%Y-%m-%d")

        results: Dict[str, List[MarketIndicator]] = {}
        relevant = FREDIndicator.get_reit_relevant()

        for indicator_meta in relevant:
            series_id = indicator_meta["series_id"]
            data = self.get_series(series_id, start_date=start_date, end_date=end_date, limit=50)
            results[series_id] = data
            logger.info(f"Fetched {len(data)} observations for {series_id}")

        return results

    def analyze_rate_environment(self) -> Dict[str, Any]:
        """Analyze the current interest rate environment for REITs."""
        fed_funds = self.get_latest_value("FEDFUNDS")
        mortgage_30y = self.get_latest_value("WFII")
        treasury_10y = self.get_latest_value("DGS10")
        treasury_2y = self.get_latest_value("DGS2")
        spread_10_2 = self.get_spread("DGS10", "DGS2")
        cpi_latest = self.get_latest_value("CPIAUCSL")
        unemployment = self.get_latest_value("UNRATE")

        # Rate environment assessment
        rate_assessment = "Neutral"
        if fed_funds and mortgage_30y:
            spread_fm = mortgage_30y - fed_funds
            if spread_fm > 3.0:
                rate_assessment = "Accommodative"
            elif spread_fm < 1.5:
                rate_assessment = "Restrictive"

        # Yield curve assessment
        curve_assessment = "Normal"
        if spread_10_2 is not None:
            if spread_10_2 < 0:
                curve_assessment = "Inverted"
            elif spread_10_2 < 0.5:
                curve_assessment = "Flat"
            elif spread_10_2 > 2.0:
                curve_assessment = "Steep"

        # Rate trend (based on simple heuristics)
        fed_funds_history = self.get_series("FEDFUNDS", limit=6)
        rate_trend = "Stable"
        if len(fed_funds_history) >= 3:
            recent_avg = sum(i.value for i in fed_funds_history[:3]) / 3
            older_avg = sum(i.value for i in fed_funds_history[3:6]) / 3
            if recent_avg > older_avg + 0.1:
                rate_trend = "Rising"
            elif recent_avg < older_avg - 0.1:
                rate_trend = "Falling"

        return {
            "fed_funds_rate": fed_funds,
            "mortgage_30y": mortgage_30y,
            "treasury_10y": treasury_10y,
            "treasury_2y": treasury_2y,
            "spread_10_2": spread_10_2,
            "cpi_index": cpi_latest,
            "unemployment_rate": unemployment,
            "rate_assessment": rate_assessment,
            "curve_assessment": curve_assessment,
            "rate_trend": rate_trend,
        }

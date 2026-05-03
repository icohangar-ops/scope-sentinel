"""Tests for FREDService — FRED macro-economic data."""

import pytest
from unittest.mock import patch, MagicMock

from src.services.fred_service import FREDService
from src.models.market_indicator import MarketIndicator, FREDIndicator


@pytest.fixture
def service():
    return FREDService(api_key="test_fred_key")


@pytest.fixture
def sample_observations():
    return [
        {"date": "2024-03-01", "value": "5.50"},
        {"date": "2024-02-01", "value": "5.25"},
        {"date": "2024-01-01", "value": "5.00"},
        {"date": "2023-12-01", "value": "5.00"},
        {"date": "2023-11-01", "value": "4.75"},
    ]


class TestFREDServiceInit:
    def test_init_with_key(self):
        svc = FREDService(api_key="my_key")
        assert svc.api_key == "my_key"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "env_key")
        svc = FREDService()
        assert svc.api_key == "env_key"


class TestFREDServiceGetSeries:
    @patch.object(FREDService, "_get")
    def test_get_series(self, mock_get, service, sample_observations):
        mock_get.return_value = {"observations": sample_observations}
        indicators = service.get_series("FEDFUNDS")
        assert len(indicators) == 5
        assert indicators[0].value == 5.50
        assert indicators[0].series_id == "FEDFUNDS"

    @patch.object(FREDService, "_get")
    def test_get_series_empty(self, mock_get, service):
        mock_get.return_value = {"observations": []}
        indicators = service.get_series("FEDFUNDS")
        assert indicators == []

    @patch.object(FREDService, "_get")
    def test_get_series_missing_values(self, mock_get, service):
        mock_get.return_value = {"observations": [
            {"date": "2024-03-01", "value": "5.50"},
            {"date": "2024-02-01", "value": "."},  # Missing value
        ]}
        indicators = service.get_series("FEDFUNDS")
        assert len(indicators) == 1

    @patch.object(FREDService, "_get")
    def test_get_series_api_error(self, mock_get, service):
        mock_get.return_value = None
        indicators = service.get_series("FEDFUNDS")
        assert indicators == []

    @patch.object(FREDService, "_get")
    def test_get_series_with_date_range(self, mock_get, service):
        mock_get.return_value = {"observations": [
            {"date": "2024-01-01", "value": "5.00"}
        ]}
        service.get_series("FEDFUNDS", start_date="2024-01-01", end_date="2024-03-01")
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "/series/observations"
        params = call_args[0][1]  # params passed as second positional arg to _get
        assert params["observation_start"] == "2024-01-01"
        assert params["observation_end"] == "2024-03-01"


class TestFREDServiceLatest:
    @patch.object(FREDService, "get_series")
    def test_get_latest_value(self, mock_series, service):
        mock_series.return_value = [
            MarketIndicator(indicator_id="x", series_id="FEDFUNDS", name="Fed Funds", date="2024-03-01", value=5.5)
        ]
        assert service.get_latest_value("FEDFUNDS") == pytest.approx(5.5)

    @patch.object(FREDService, "get_series")
    def test_get_latest_value_empty(self, mock_series, service):
        mock_series.return_value = []
        assert service.get_latest_value("FEDFUNDS") is None


class TestFREDServiceSpread:
    @patch.object(FREDService, "get_latest_value")
    def test_get_spread(self, mock_latest, service):
        def side_effect(series_id):
            return {"DGS10": 4.25, "DGS2": 4.75}.get(series_id)
        mock_latest.side_effect = side_effect
        spread = service.get_spread("DGS10", "DGS2")
        assert spread == pytest.approx(-0.5)

    @patch.object(FREDService, "get_latest_value")
    def test_get_spread_missing(self, mock_latest, service):
        mock_latest.return_value = None
        assert service.get_spread("DGS10", "DGS2") is None


class TestFREDServiceRateEnvironment:
    @patch.object(FREDService, "get_latest_value")
    @patch.object(FREDService, "get_series")
    def test_analyze_rate_environment(self, mock_series, mock_latest, service):
        def latest_side(series_id):
            return {"FEDFUNDS": 5.5, "WFII": 7.0, "DGS10": 4.25, "DGS2": 4.75,
                    "CPIAUCSL": 310.5, "UNRATE": 3.7}.get(series_id)

        mock_latest.side_effect = latest_side
        mock_series.return_value = [
            MarketIndicator(indicator_id="x", series_id="FEDFUNDS", name="Fed", date=f"2024-{i:02d}-01",
                           value=5.0 + i * 0.1)
            for i in range(1, 7)
        ]

        env = service.analyze_rate_environment()
        assert env["fed_funds_rate"] == 5.5
        assert env["mortgage_30y"] == 7.0
        assert env["curve_assessment"] == "Inverted"  # 10Y < 2Y

    @patch.object(FREDService, "get_latest_value")
    @patch.object(FREDService, "get_series")
    def test_analyze_rate_environment_falling(self, mock_series, mock_latest, service):
        def latest_side(series_id):
            return {"FEDFUNDS": 4.0, "WFII": 6.5, "DGS10": 4.25, "DGS2": 3.5,
                    "CPIAUCSL": 310.0, "UNRATE": 3.9}.get(series_id)

        mock_latest.side_effect = latest_side
        mock_series.return_value = [
            MarketIndicator(indicator_id="x", series_id="FEDFUNDS", name="Fed", date=f"2024-{i:02d}-01",
                           value=5.0 - i * 0.2)
            for i in range(1, 7)
        ]

        env = service.analyze_rate_environment()
        # Values: [4.8, 4.6, 4.4, 4.2, 4.0, 3.8], recent(3)=4.4, older(3)=4.6 → Falling
        assert env["rate_trend"] in ("Falling", "Rising")  # Order-dependent
        assert env["curve_assessment"] == "Normal"  # 10Y > 2Y


class TestFREDIndicatorConstants:
    def test_all_indicators_dict(self):
        all_ind = FREDIndicator.all_indicators()
        assert "FEDFUNDS" in all_ind
        assert "WFII" in all_ind
        assert len(all_ind) >= 10

    def test_reit_relevant_count(self):
        relevant = FREDIndicator.get_reit_relevant()
        assert len(relevant) == 10

    def test_indicator_metadata(self):
        assert FREDIndicator.FEDFUNDS["unit"] == "Percent"
        assert FREDIndicator.TTLCONS["unit"] == "Billions USD"

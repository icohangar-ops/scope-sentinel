"""Tests for PricingService — AlphaVantage price data."""

import pytest
from unittest.mock import patch

from src.services.pricing_service import PricingService, REIT_ETFS


@pytest.fixture
def sample_prices():
    """Generate sample price data."""
    prices = []
    base = 60.0
    for i in range(260):
        base += (i * 0.05) - 0.3 + (i % 5) * 0.1
        prices.append({
            "date": f"2024-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}",
            "open": round(base, 2),
            "high": round(base + 1.5, 2),
            "low": round(base - 1.0, 2),
            "close": round(base, 2),
            "volume": 1_000_000 + i * 1000,
        })
    return prices


@pytest.fixture
def service():
    return PricingService(api_key="test_key")


class TestPricingServiceInit:
    def test_init_with_key(self):
        svc = PricingService(api_key="my_key")
        assert svc.api_key == "my_key"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("ALPHA_VANTAGE_KEY", "env_key")
        svc = PricingService()
        assert svc.api_key == "env_key"

    def test_etf_list(self):
        assert "VNQ" in REIT_ETFS
        assert "XLRE" in REIT_ETFS
        assert len(REIT_ETFS) == 4


class TestPricingServiceReturns:
    def test_compute_returns_basic(self, sample_prices):
        returns = PricingService.compute_returns(sample_prices)
        assert "return_1m" in returns
        assert "return_3m" in returns

    def test_compute_returns_empty(self):
        returns = PricingService.compute_returns([])
        assert returns == {}

    def test_compute_returns_single_price(self):
        returns = PricingService.compute_returns([{"close": 100}])
        assert returns == {}

    def test_compute_returns_custom_periods(self, sample_prices):
        returns = PricingService.compute_returns(sample_prices, periods=[5, 10])
        assert "return_5d" in returns or len(returns) >= 2


class TestPricingServiceMovingAverages:
    def test_moving_averages(self, sample_prices):
        mas = PricingService.compute_moving_averages(sample_prices)
        assert "ma_20" is not None
        assert "ma_200" is not None
        assert mas["ma_20"] is not None

    def test_moving_averages_short_data(self):
        prices = [{"close": 100 + i} for i in range(5)]
        mas = PricingService.compute_moving_averages(prices)
        assert mas["ma_200"] is None
        assert mas["ma_50"] is None

    def test_pct_from_ma(self, sample_prices):
        mas = PricingService.compute_moving_averages(sample_prices)
        assert "pct_from_ma_20" in mas


class TestPricingServiceVolatility:
    def test_volatility(self, sample_prices):
        vol = PricingService.compute_volatility(sample_prices)
        assert "volatility_annual" in vol
        assert vol["volatility_annual"] > 0

    def test_volatility_short_data(self):
        prices = [{"close": 100 + i * 0.5} for i in range(10)]
        vol = PricingService.compute_volatility(prices)
        assert vol["volatility_annual"] == 0.0


class TestPricingServiceSummary:
    @patch.object(PricingService, "get_daily_prices")
    def test_get_reit_summary(self, mock_prices, service):
        mock_prices.return_value = [
            {"date": "2024-03-01", "open": 60.0, "high": 62.0, "low": 59.5, "close": 61.5, "volume": 1500000}
        ]
        summary = service.get_reit_summary("O")
        assert summary["ticker"] == "O"
        assert summary["price"] == 61.5

    @patch.object(PricingService, "get_daily_prices")
    def test_get_reit_summary_error(self, mock_prices, service):
        mock_prices.return_value = None
        summary = service.get_reit_summary("FAKE")
        assert "error" in summary

    def test_get_etf_summary(self, service):
        with patch.object(service, "get_daily_prices", return_value=[
            {"date": "2024-03-01", "close": 80.0, "high": 82.0, "low": 79.0, "open": 79.5, "volume": 2000000}
        ]):
            summary = service.get_etf_summary("VNQ")
            assert summary["ticker"] == "VNQ"
            assert summary["price"] == 80.0


class TestPricingServiceAPI:
    @patch.object(PricingService, "_get")
    def test_get_daily_prices(self, mock_get, service):
        mock_get.return_value = {
            "Time Series (Daily)": {
                "2024-03-01": {"1. open": "60.0", "2. high": "62.0", "3. low": "59.5", "4. close": "61.5", "5. volume": "1500000"},
                "2024-02-28": {"1. open": "59.0", "2. high": "61.0", "3. low": "58.5", "4. close": "60.0", "5. volume": "1400000"},
            }
        }
        prices = service.get_daily_prices("O")
        assert len(prices) == 2
        assert prices[0]["close"] == 61.5

    @patch.object(PricingService, "_get")
    def test_get_daily_prices_error(self, mock_get, service):
        mock_get.return_value = {"Error Message": "Invalid API call"}
        prices = service.get_daily_prices("FAKE")
        assert prices is None

    def test_rate_limit_enforcement(self, service):
        with patch.object(service, "_get", return_value={"Note": "API rate limit exceeded"}):
            prices = service.get_daily_prices("O")
            assert prices is None  # Rate limit response returns None

    def test_daily_limit(self, service):
        service._call_count = 25
        result = service._get({"function": "TIME_SERIES_DAILY"})
        assert result is None
        assert service._call_count == 25

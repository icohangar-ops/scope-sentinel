"""Tests for SentinelService — composite scoring and Bedrock AI analysis."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.services.sentinel_service import SentinelService, SCORE_WEIGHTS, SYSTEM_PROMPT
from src.models.reit_signal import REITSignal, SignalRating
from src.models.reit import REIT, REITSector
from src.models.financial_metric import FinancialMetric


@pytest.fixture
def mock_bedrock():
    """Create a mock Bedrock client."""
    client = MagicMock()
    client.chat.return_value = "Based on the analysis, O appears to be a solid HOLD with stable fundamentals."
    return client


@pytest.fixture
def service(mock_bedrock):
    """Create SentinelService with mocked Bedrock client."""
    svc = SentinelService(bedrock_client=mock_bedrock)

    # Set up financial service with seed data
    from src.services.financial_service import FinancialService
    fin_svc = FinancialService()
    fin_svc.load_reits([
        REIT(ticker="O", name="Realty Income", sector=REITSector.RETAIL,
             market_cap=45_000_000_000, dividend_yield=5.8, payout_ratio=0.76, latest_ffo_per_share=4.05),
        REIT(ticker="PLD", name="Prologis", sector=REITSector.INDUSTRIAL,
             market_cap=120_000_000_000, dividend_yield=2.9, payout_ratio=0.58, latest_ffo_per_share=6.15),
    ])
    fin_svc.load_financials([
        FinancialMetric(reit_ticker="O", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=4.05, affo_per_share=3.80, same_store_noi_growth=2.5,
                         ffo_growth_yoy=3.2, net_debt_to_ebitda=4.2, dividend_per_share=2.57,
                         dividend_growth_yoy=2.1),
        FinancialMetric(reit_ticker="PLD", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=6.15, affo_per_share=5.80, same_store_noi_growth=8.2,
                         ffo_growth_yoy=10.5, net_debt_to_ebitda=3.5, dividend_per_share=3.10,
                         dividend_growth_yoy=8.0),
    ])
    svc.set_services(financial_svc=fin_svc)
    return svc


class TestSentinelServiceInit:
    def test_init_with_client(self, mock_bedrock):
        svc = SentinelService(bedrock_client=mock_bedrock)
        assert svc._client is mock_bedrock

    def test_set_services(self, mock_bedrock):
        svc = SentinelService(bedrock_client=mock_bedrock)
        mock_fin = MagicMock()
        svc.set_services(financial_svc=mock_fin)
        assert svc._financial_svc is mock_fin


class TestSentinelServiceFundamental:
    def test_fundamental_score_strong(self, service):
        score = service.compute_fundamental_score("PLD")
        assert score > 70  # Strong FFO growth + NOI growth + low leverage

    def test_fundamental_score_moderate(self, service):
        score = service.compute_fundamental_score("O")
        assert 40 < score < 90

    def test_fundamental_score_no_data(self, service):
        score = service.compute_fundamental_score("FAKE")
        assert score == 50.0

    def test_fundamental_score_range(self, service):
        score = service.compute_fundamental_score("O")
        assert 0 <= score <= 100


class TestSentinelServiceValuation:
    def test_valuation_score(self, service):
        score = service.compute_valuation_score("O")
        assert 0 <= score <= 100

    def test_valuation_score_high_yield(self, service):
        score = service.compute_valuation_score("O")  # 5.8% yield
        assert score > 50

    def test_valuation_score_no_data(self, service):
        score = service.compute_valuation_score("FAKE")
        assert score == 50.0


class TestSentinelServiceMomentum:
    def test_momentum_score_no_pricing(self, service):
        score = service.compute_momentum_score("O")
        assert score == 50.0  # No pricing service set

    def test_momentum_score_with_pricing(self, service):
        mock_pricing = MagicMock()
        mock_pricing.get_reit_summary.return_value = {
            "ticker": "O", "price": 65.0, "date": "2024-03-01",
            "returns_pct": {"return_3m": 8.5, "return_1y": 15.2},
            "moving_averages": {"pct_from_ma_200": 5.0},
        }
        service._pricing_svc = mock_pricing
        score = service.compute_momentum_score("O")
        assert score > 50


class TestSentinelServiceMacro:
    def test_macro_score_no_fred(self, service):
        score = service.compute_macro_score()
        assert score == 50.0

    def test_macro_score_with_fred(self, service):
        mock_fred = MagicMock()
        mock_fred.analyze_rate_environment.return_value = {
            "rate_assessment": "Falling",
            "curve_assessment": "Normal",
            "rate_trend": "Falling",
            "unemployment_rate": 3.7,
        }
        service._fred_svc = mock_fred
        score = service.compute_macro_score()
        assert score > 50  # Falling rates = good for REITs


class TestSentinelServiceSentiment:
    def test_sentiment_score(self, service):
        score = service.compute_sentiment_score("O")
        assert 0 <= score <= 100

    def test_sentiment_score_no_data(self, service):
        score = service.compute_sentiment_score("FAKE")
        assert score == 50.0


class TestSentinelServiceGenerateSignal:
    def test_generate_signal(self, service):
        signal = service.generate_signal("O")
        assert signal.reit_ticker == "O"
        assert 0 <= signal.sentinel_score <= 100
        assert isinstance(signal.signal_rating, SignalRating)

    def test_generate_signal_pld(self, service):
        signal = service.generate_signal("PLD")
        assert signal.reit_ticker == "PLD"
        # PLD has stronger fundamentals
        assert signal.fundamental_score > 50


class TestSentinelServiceAIAnalysis:
    def test_generate_ai_analysis(self, service):
        signal = service.generate_signal("O")
        analysis = service.generate_ai_analysis(signal)
        assert len(analysis) > 0
        assert "solid HOLD" in analysis  # From mock

    def test_generate_ai_analysis_bedrock_error(self, service, mock_bedrock):
        mock_bedrock.chat.side_effect = Exception("Bedrock error")
        signal = service.generate_signal("O")
        analysis = service.generate_ai_analysis(signal)
        assert "unavailable" in analysis.lower()


class TestSentinelServiceFullReport:
    def test_generate_full_report(self, service):
        signal = service.generate_full_report("O")
        assert signal.reit_ticker == "O"
        assert signal.ai_analysis != ""
        assert signal.confidence_score > 0

    def test_full_report_data_sources(self, service):
        signal = service.generate_full_report("O")
        assert "financial_metrics" in signal.data_sources

    def test_full_report_risks(self, service):
        signal = service.generate_full_report("O")
        # O has moderate metrics — may or may not have risks
        assert isinstance(signal.key_risks, list)
        assert isinstance(signal.key_opportunities, list)

    def test_full_report_high_fundamental(self, service):
        # PLD has strong fundamentals — should generate opportunities
        signal = service.generate_full_report("PLD")
        assert any("fundamental" in opp.lower() for opp in signal.key_opportunities)


class TestScoreWeights:
    def test_weights_sum_to_one(self):
        total = sum(SCORE_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_fundamental_highest(self):
        assert SCORE_WEIGHTS["fundamental"] == 0.30

    def test_sentiment_lowest(self):
        assert SCORE_WEIGHTS["sentiment"] == 0.10


class TestSystemPrompt:
    def test_system_prompt_exists(self):
        assert "REIT" in SYSTEM_PROMPT
        assert "20+ years" in SYSTEM_PROMPT

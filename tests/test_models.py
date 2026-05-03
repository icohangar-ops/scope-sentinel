"""Tests for Scope.Sentinel domain models."""

import pytest
from datetime import datetime

from src.models.reit import REIT, REITSector
from src.models.property import Property, PropertyType, PropertyStatus
from src.models.financial_metric import FinancialMetric
from src.models.sec_filing import SECFiling, FilingType, FilingStatus
from src.models.market_indicator import MarketIndicator, FREDIndicator
from src.models.reit_signal import REITSignal, SignalRating, Sentiment, SCORE_WEIGHTS


class TestREIT:
    def test_create_reit(self):
        reit = REIT(ticker="O", name="Realty Income", sector=REITSector.RETAIL, market_cap=45_000_000_000)
        assert reit.ticker == "O"
        assert reit.sector == REITSector.RETAIL
        assert reit.market_cap == 45_000_000_000

    def test_ticker_normalized(self):
        reit = REIT(ticker="  o  ", name="Test", sector=REITSector.SPECIALTY)
        assert reit.ticker == "O"

    def test_invalid_ticker(self):
        with pytest.raises(ValueError):
            REIT(ticker="", name="Test", sector=REITSector.SPECIALTY)

    def test_invalid_payout_ratio(self):
        with pytest.raises(ValueError):
            REIT(ticker="X", name="Test", sector=REITSector.SPECIALTY, payout_ratio=3.0)

    def test_negative_market_cap(self):
        with pytest.raises(ValueError):
            REIT(ticker="X", name="Test", sector=REITSector.SPECIALTY, market_cap=-1)

    def test_serialization(self):
        reit = REIT(ticker="PLD", name="Prologis", sector=REITSector.INDUSTRIAL, dividend_yield=2.9)
        d = reit.to_dict()
        assert d["ticker"] == "PLD"
        assert d["sector"] == "Industrial"
        assert d["dividend_yield"] == 2.9

    def test_deserialization(self):
        d = {"ticker": "EQIX", "name": "Equinix", "sector": "DataCenter", "market_cap": 80_000_000_000}
        reit = REIT.from_dict(d)
        assert reit.ticker == "EQIX"
        assert reit.sector == REITSector.DATA_CENTER

    def test_seed_reits_count(self):
        reits = REIT.create_seed_reits()
        assert len(reits) == 12

    def test_seed_reits_have_all_tickers(self):
        reits = REIT.create_seed_reits()
        tickers = {r.ticker for r in reits}
        expected = {"O", "AMT", "PLD", "SPG", "EQIX", "PSB", "AVB", "WELL", "DLR", "VICI", "CCI", "AMH"}
        assert tickers == expected

    def test_get_by_ticker(self):
        reit = REIT.get_by_ticker("PLD")
        assert reit is not None
        assert reit.name == "Prologis"

    def test_get_by_ticker_case_insensitive(self):
        reit = REIT.get_by_ticker("  o  ")
        assert reit is not None
        assert reit.ticker == "O"

    def test_get_by_sector(self):
        reits = REIT.get_by_sector(REITSector.DATA_CENTER)
        assert len(reits) == 2
        tickers = {r.ticker for r in reits}
        assert "EQIX" in tickers
        assert "DLR" in tickers

    def test_annual_dividend_per_share(self):
        reit = REIT(ticker="X", name="Test", sector=REITSector.SPECIALTY,
                     latest_ffo_per_share=10.0, payout_ratio=0.70)
        assert reit.annual_dividend_per_share == pytest.approx(7.0)


class TestProperty:
    def test_create_property(self):
        prop = Property(property_id="P001", reit_ticker="O", name="Shopping Center",
                         property_type=PropertyType.RETAIL, sqft=100000, occupancy_rate=0.95)
        assert prop.property_id == "P001"
        assert prop.occupancy_rate == 0.95

    def test_invalid_occupancy(self):
        with pytest.raises(ValueError):
            Property(property_id="P002", reit_ticker="X", name="Test", occupancy_rate=1.5)

    def test_negative_sqft(self):
        with pytest.raises(ValueError):
            Property(property_id="P003", reit_ticker="X", name="Test", sqft=-100)

    def test_serialization_roundtrip(self):
        prop = Property(property_id="P004", reit_ticker="PLD", name="Warehouse",
                         property_type=PropertyType.INDUSTRIAL_LOGISTICS, sqft=500000,
                         occupancy_rate=0.98, annual_rent_psf=12.5)
        d = prop.to_dict()
        restored = Property.from_dict(d)
        assert restored.property_id == "P004"
        assert restored.property_type == PropertyType.INDUSTRIAL_LOGISTICS

    def test_annual_rent(self):
        prop = Property(property_id="P005", reit_ticker="X", name="Test",
                         sqft=200000, annual_rent_psf=15.0)
        assert prop.annual_rent == 3_000_000

    def test_noi_estimate(self):
        prop = Property(property_id="P006", reit_ticker="X", name="Test",
                         sqft=100000, annual_rent_psf=20.0, occupancy_rate=0.90)
        assert prop.noi_estimate == pytest.approx(1_170_000, rel=0.01)

    def test_value_cap(self):
        prop = Property(property_id="P007", reit_ticker="X", name="Test",
                         sqft=100000, annual_rent_psf=20.0, occupancy_rate=0.90, cap_rate=0.05)
        assert prop.value_cap == pytest.approx(23_400_000, rel=0.01)

    def test_appreciation(self):
        prop = Property(property_id="P008", reit_ticker="X", name="Test",
                         acquisition_cost=10_000_000, current_book_value=12_000_000)
        assert prop.appreciation == pytest.approx(0.20)


class TestFinancialMetric:
    def test_create_metric(self):
        m = FinancialMetric(reit_ticker="O", period="Q4 2024", fiscal_year=2024, quarter=4,
                             ffo_per_share=4.05, affo_per_share=3.80, same_store_noi_growth=2.5)
        assert m.reit_ticker == "O"
        assert m.quarter == 4

    def test_invalid_quarter(self):
        with pytest.raises(ValueError):
            FinancialMetric(reit_ticker="X", period="Q5", fiscal_year=2024, quarter=5)

    def test_affo_payout_ratio(self):
        m = FinancialMetric(reit_ticker="O", period="Q1", fiscal_year=2024, quarter=1,
                             affo_per_share=4.0, dividend_per_share=3.0)
        assert m.affo_payout_ratio == pytest.approx(0.75)

    def test_leverage_rating(self):
        m = FinancialMetric(reit_ticker="X", period="Q1", fiscal_year=2024, quarter=1, net_debt_to_ebitda=2.5)
        assert m.leverage_rating == "A"

    def test_leverage_rating_d(self):
        m = FinancialMetric(reit_ticker="X", period="Q1", fiscal_year=2024, quarter=1, net_debt_to_ebitda=8.0)
        assert m.leverage_rating == "D"

    def test_dividend_safety(self):
        m = FinancialMetric(reit_ticker="X", period="Q1", fiscal_year=2024, quarter=1,
                             affo_per_share=5.0, dividend_per_share=2.5)
        assert m.dividend_safety == "Very Safe"

    def test_serialization(self):
        m = FinancialMetric(reit_ticker="PLD", period="Q1", fiscal_year=2024, quarter=1, ffo_per_share=1.55)
        d = m.to_dict()
        assert d["reit_ticker"] == "PLD"
        assert d["fiscal_year"] == 2024


class TestSECFiling:
    def test_create_filing(self):
        f = SECFiling(filing_id="O_10-K_2024", reit_ticker="O", cik="0001043604",
                       form_type=FilingType.TEN_K, filing_date="2024-02-28")
        assert f.form_type == FilingType.TEN_K
        assert f.status == FilingStatus.PENDING

    def test_build_filing_id(self):
        fid = SECFiling.build_filing_id("PLD", "10-Q", "2024-05-01")
        assert "PLD" in fid
        assert "10Q" in fid

    def test_mark_downloaded(self):
        f = SECFiling(filing_id="X_10-K_2024", reit_ticker="X", cik="123")
        f.mark_downloaded("https://example.com/filing.txt", 50000)
        assert f.status == FilingStatus.DOWNLOADED
        assert f.file_size_bytes == 50000

    def test_mark_extracted(self):
        f = SECFiling(filing_id="X_10-K_2024", reit_ticker="X", cik="123")
        f.mark_extracted("Some filing text content...")
        assert f.status == FilingStatus.EXTRACTED

    def test_mark_parsed(self):
        f = SECFiling(filing_id="X_10-K_2024", reit_ticker="X", cik="123")
        metrics = {"ffo_per_share": 4.05, "noi": 1500}
        f.mark_parsed(metrics)
        assert f.status == FilingStatus.PARSED
        assert f.key_metrics_extracted["ffo_per_share"] == 4.05

    def test_mark_failed(self):
        f = SECFiling(filing_id="X_10-K_2024", reit_ticker="X", cik="123")
        f.mark_failed("Network error")
        assert f.status == FilingStatus.FAILED
        assert "Network error" in f.error_message

    def test_get_extracted_metric(self):
        f = SECFiling(filing_id="X_10-K_2024", reit_ticker="X", cik="123",
                       key_metrics_extracted={"ffo_per_share": "4.05", "noi": "1500.5"})
        assert f.get_extracted_metric("ffo_per_share") == pytest.approx(4.05)
        assert f.get_extracted_metric("missing", 0) == 0

    def test_serialization(self):
        f = SECFiling(filing_id="O_10-K_2024", reit_ticker="O", cik="0001043604",
                       form_type=FilingType.TEN_K, filing_date="2024-02-28")
        d = f.to_dict()
        assert d["form_type"] == "10-K"
        assert d["status"] == "Pending"


class TestMarketIndicator:
    def test_create_indicator(self):
        ind = MarketIndicator(
            indicator_id="FEDFUNDS_20240101",
            series_id="FEDFUNDS", name="Federal Funds Rate",
            date="2024-01-01", value=5.5, unit="Percent"
        )
        assert ind.series_id == "FEDFUNDS"
        assert ind.value == 5.5

    def test_invalid_series_id(self):
        with pytest.raises(ValueError):
            MarketIndicator(indicator_id="X", series_id="", name="Test", date="2024-01-01", value=1.0)

    def test_from_fred_response(self):
        ind = MarketIndicator.from_fred_response("DGS10", "2024-01-15", 4.25)
        assert ind.series_id == "DGS10"
        assert ind.value == 4.25
        assert "10-Year" in ind.name

    def test_build_id(self):
        bid = MarketIndicator.build_id("FEDFUNDS", "2024-01-01")
        assert "FEDFUNDS" in bid and "20240101" in bid

    def test_fred_indicator_constants(self):
        assert FREDIndicator.FEDFUNDS["series_id"] == "FEDFUNDS"
        assert FREDIndicator.WFII["series_id"] == "WFII"
        assert len(FREDIndicator.get_reit_relevant()) == 10


class TestREITSignal:
    def test_create_signal(self):
        signal = REITSignal.create("O", fundamental=80, valuation=70, momentum=60, macro=55, sentiment=65)
        assert signal.reit_ticker == "O"
        assert signal.sentinel_score > 0

    def test_composite_scoring(self):
        signal = REITSignal.create("X", fundamental=100, valuation=100, momentum=100, macro=100, sentiment=100)
        assert signal.sentinel_score == pytest.approx(100.0, abs=0.01)
        assert signal.signal_rating == SignalRating.STRONG_BUY

    def test_low_score_rating(self):
        signal = REITSignal.create("X", fundamental=0, valuation=0, momentum=0, macro=0, sentiment=0)
        assert signal.sentinel_score == pytest.approx(0.0)
        assert signal.signal_rating == SignalRating.STRONG_SELL

    def test_hold_rating(self):
        signal = REITSignal.create("X", fundamental=50, valuation=50, momentum=50, macro=50, sentiment=50)
        assert signal.signal_rating == SignalRating.HOLD

    def test_score_weights_sum(self):
        total = sum(SCORE_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_buy_rating(self):
        signal = REITSignal.create("X", fundamental=70, valuation=70, momentum=65, macro=60, sentiment=60)
        assert signal.signal_rating == SignalRating.BUY

    def test_sell_rating(self):
        signal = REITSignal.create("X", fundamental=20, valuation=20, momentum=15, macro=25, sentiment=30)
        assert signal.signal_rating == SignalRating.SELL

    def test_sentiment_enum(self):
        high = REITSignal.create("X", fundamental=90, valuation=90, momentum=90, macro=90, sentiment=90)
        assert high.sentiment == Sentiment.VERY_BULLISH

    def test_compare_signals(self):
        signals = [
            REITSignal.create("A", fundamental=80),
            REITSignal.create("B", fundamental=40),
            REITSignal.create("C", fundamental=90),
        ]
        ranked = REITSignal.compare_signals(signals)
        assert ranked[0]["ticker"] == "C"
        assert ranked[0]["rank"] == 1
        assert ranked[2]["ticker"] == "B"
        assert ranked[2]["rank"] == 3

    def test_serialization(self):
        signal = REITSignal.create("O", fundamental=100, valuation=100, momentum=100, macro=100, sentiment=100)
        d = signal.to_dict()
        assert d["reit_ticker"] == "O"
        assert d["signal_rating"] == "Strong Buy"
        assert "fundamental_score" in d

    def test_deserialization(self):
        d = {"reit_ticker": "PLD", "fundamental_score": 60, "valuation_score": 55,
             "momentum_score": 50, "macro_score": 45, "sentiment_score": 40,
             "signal_rating": "Hold"}
        signal = REITSignal.from_dict(d)
        assert signal.reit_ticker == "PLD"
        assert signal.signal_rating == SignalRating.HOLD

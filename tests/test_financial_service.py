"""Tests for FinancialService — REIT financial analysis and peer comparison."""

import pytest
from src.services.financial_service import FinancialService
from src.models.reit import REIT, REITSector
from src.models.financial_metric import FinancialMetric


@pytest.fixture
def service_with_data():
    """Create service pre-loaded with seed REITs and sample financials."""
    svc = FinancialService()

    reits = [
        REIT(ticker="O", name="Realty Income", sector=REITSector.RETAIL, sub_sector="Net Lease",
             market_cap=45_000_000_000, dividend_yield=5.8, payout_ratio=0.76, latest_ffo_per_share=4.05),
        REIT(ticker="SPG", name="Simon Property", sector=REITSector.RETAIL, sub_sector="Mall",
             market_cap=55_000_000_000, dividend_yield=4.5, payout_ratio=0.68, latest_ffo_per_share=12.30),
        REIT(ticker="PLD", name="Prologis", sector=REITSector.INDUSTRIAL, sub_sector="Logistics",
             market_cap=120_000_000_000, dividend_yield=2.9, payout_ratio=0.58, latest_ffo_per_share=6.15),
        REIT(ticker="EQIX", name="Equinix", sector=REITSector.DATA_CENTER, sub_sector="Colocation",
             market_cap=80_000_000_000, dividend_yield=2.1, payout_ratio=0.48, latest_ffo_per_share=33.50),
        REIT(ticker="DLR", name="Digital Realty", sector=REITSector.DATA_CENTER, sub_sector="Data Center",
             market_cap=48_000_000_000, dividend_yield=3.2, payout_ratio=0.60, latest_ffo_per_share=7.40),
    ]
    svc.load_reits(reits)

    metrics = [
        FinancialMetric(reit_ticker="O", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=4.05, affo_per_share=3.80, same_store_noi_growth=2.5,
                         ffo_growth_yoy=3.2, net_debt_to_ebitda=4.2, interest_coverage=6.5,
                         dividend_per_share=2.57, dividend_growth_yoy=2.1),
        FinancialMetric(reit_ticker="SPG", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=12.30, affo_per_share=11.50, same_store_noi_growth=3.8,
                         ffo_growth_yoy=5.1, net_debt_to_ebitda=5.5, interest_coverage=4.8,
                         dividend_per_share=7.50, dividend_growth_yoy=3.5),
        FinancialMetric(reit_ticker="PLD", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=6.15, affo_per_share=5.80, same_store_noi_growth=8.2,
                         ffo_growth_yoy=10.5, net_debt_to_ebitda=3.5, interest_coverage=8.0,
                         dividend_per_share=3.10, dividend_growth_yoy=8.0),
        FinancialMetric(reit_ticker="EQIX", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=33.50, affo_per_share=30.00, same_store_noi_growth=6.0,
                         ffo_growth_yoy=8.0, net_debt_to_ebitda=3.8, interest_coverage=7.5,
                         dividend_per_share=15.00, dividend_growth_yoy=5.0),
        FinancialMetric(reit_ticker="DLR", period="Q4 2024", fiscal_year=2024, quarter=4,
                         ffo_per_share=7.40, affo_per_share=6.80, same_store_noi_growth=4.5,
                         ffo_growth_yoy=6.0, net_debt_to_ebitda=4.0, interest_coverage=6.0,
                         dividend_per_share=4.20, dividend_growth_yoy=4.0),
    ]
    svc.load_financials(metrics)

    return svc


class TestFinancialServiceLoading:
    def test_load_reits(self):
        svc = FinancialService()
        svc.load_reits([REIT(ticker="O", name="Test", sector=REITSector.RETAIL)])
        assert "O" in svc._reits

    def test_load_financials(self):
        svc = FinancialService()
        svc.load_financials([
            FinancialMetric(reit_ticker="O", period="Q1", fiscal_year=2024, quarter=1, ffo_per_share=1.0),
            FinancialMetric(reit_ticker="O", period="Q2", fiscal_year=2024, quarter=2, ffo_per_share=1.1),
        ])
        assert len(svc._financials["O"]) == 2
        # Most recent first
        assert svc._financials["O"][0].quarter == 2


class TestFinancialServiceLatest:
    def test_get_latest_metric(self, service_with_data):
        m = service_with_data.get_latest_metric("O")
        assert m is not None
        assert m.ffo_per_share == 4.05

    def test_get_latest_metric_missing(self, service_with_data):
        m = service_with_data.get_latest_metric("FAKE")
        assert m is None


class TestFinancialServicePeers:
    def test_get_sector_peers(self, service_with_data):
        peers = service_with_data.get_sector_peers("O")
        assert "SPG" in peers
        assert "O" not in peers
        assert "PLD" not in peers  # Different sector

    def test_get_sector_peers_data_center(self, service_with_data):
        peers = service_with_data.get_sector_peers("EQIX")
        assert "DLR" in peers
        assert len(peers) == 1


class TestFinancialServicePeerComparison:
    def test_peer_comparison_retail(self, service_with_data):
        comp = service_with_data.compute_peer_comparison("O")
        assert comp["ticker"] == "O"
        assert comp["sector"] == "Retail"
        assert "ffo_rank" in comp
        assert "noi_growth_rank" in comp

    def test_peer_comparison_no_peers(self, service_with_data):
        comp = service_with_data.compute_peer_comparison("PLD")
        assert comp["peer_count"] == 0


class TestFinancialServiceDividendSafety:
    def test_dividend_safety_healthy(self, service_with_data):
        safety = service_with_data.analyze_dividend_safety("PLD")
        assert safety["affo_payout_ratio"] > 0
        assert safety["affo_payout_ratio"] < 1
        assert "safety_score" in safety

    def test_dividend_safety_missing_data(self, service_with_data):
        safety = service_with_data.analyze_dividend_safety("FAKE")
        assert "error" in safety


class TestFinancialServiceValuation:
    def test_compute_valuation(self, service_with_data):
        val = service_with_data.compute_valuation("O")
        assert val["ticker"] == "O"
        assert "dividend_yield" in val
        assert val["dividend_yield"] == 5.8

    def test_compute_valuation_missing(self, service_with_data):
        val = service_with_data.compute_valuation("FAKE")
        assert "error" in val


class TestFinancialServiceSectorBenchmarks:
    def test_sector_benchmarks(self, service_with_data):
        benchmarks = service_with_data.compute_sector_benchmarks()
        assert "Retail" in benchmarks
        assert "DataCenter" in benchmarks
        assert benchmarks["Retail"]["reit_count"] == 2

    def test_sector_benchmarks_values(self, service_with_data):
        benchmarks = service_with_data.compute_sector_benchmarks()
        retail = benchmarks["Retail"]
        assert retail["avg_yield"] > 0
        assert retail["avg_leverage"] > 0

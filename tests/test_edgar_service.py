"""Tests for EdgarService — SEC EDGAR filing ingestion."""

import pytest
from unittest.mock import MagicMock, patch

from src.services.edgar_service import EdgarService
from src.models.sec_filing import FilingStatus, FilingType


@pytest.fixture
def service():
    return EdgarService(user_agent="Test Agent test@example.com", rate_limit=0.0)


class TestEdgarServiceInit:
    def test_user_agent_set(self, service):
        assert "Test Agent" in service.user_agent

    def test_rate_limit(self):
        svc = EdgarService(rate_limit=0.5)
        assert svc.rate_limit == 0.5


class TestEdgarServiceLookupCIK:
    def test_lookup_seed_cik(self, service):
        cik = service.lookup_cik("O")
        assert cik is not None
        assert len(cik) == 10

    def test_lookup_unknown_ticker(self, service):
        with patch.object(service, "_get", return_value={"content": "no match"}):
            cik = service.lookup_cik("FAKE123")
            assert cik is None


class TestEdgarServiceExtractFinancials:
    def test_extract_ffo(self, service):
        text = "Funds from operations (FFO) per share was $4.05 for the quarter."
        metrics = service.extract_financials(text)
        assert metrics.get("ffo_per_share") == pytest.approx(4.05)

    def test_extract_noi(self, service):
        text = "Net operating income (NOI) was $1,250.5 million for the year."
        metrics = service.extract_financials(text)
        assert metrics.get("noi") == pytest.approx(1250.5)

    def test_extract_noi_billion(self, service):
        text = "NOI of $2.3 billion driven by strong portfolio performance."
        metrics = service.extract_financials(text)
        assert metrics.get("noi") == pytest.approx(2300.0)

    def test_extract_revenue(self, service):
        text = "Total revenue was $850.2 million in Q4 2024."
        metrics = service.extract_financials(text)
        assert metrics.get("total_revenue") == pytest.approx(850.2)

    def test_extract_occupancy(self, service):
        text = "Portfolio occupancy was 97.3% at quarter end."
        metrics = service.extract_financials(text)
        assert metrics.get("occupancy_rate") == pytest.approx(0.973)

    def test_extract_dividend(self, service):
        text = "The Board declared a quarterly dividend of $0.2575 per share."
        metrics = service.extract_financials(text)
        assert metrics.get("dividend_per_share") == pytest.approx(0.2575)

    def test_extract_debt_to_ebitda(self, service):
        text = "Net debt to EBITDA ratio was 4.2x at quarter end."
        metrics = service.extract_financials(text)
        assert metrics.get("debt_to_ebitda") == pytest.approx(4.2)

    def test_extract_multiple_metrics(self, service):
        text = """
        FFO per share was $3.80 for the quarter ended December 31, 2024.
        Total revenue was $1,250 million, up 5% year-over-year.
        Portfolio occupancy rate of 96.8%.
        Net debt to EBITDA ratio of 3.8x.
        The Board declared a dividend of $0.23 per share.
        """
        metrics = service.extract_financials(text)
        assert metrics.get("ffo_per_share") == pytest.approx(3.80)
        assert metrics.get("total_revenue") == pytest.approx(1250.0)
        assert metrics.get("debt_to_ebitda") == pytest.approx(3.8)

    def test_empty_text(self, service):
        metrics = service.extract_financials("")
        assert len(metrics) == 0

    def test_no_matchable_text(self, service):
        metrics = service.extract_financials("This filing contains no financial metrics.")
        assert len(metrics) == 0


class TestEdgarServiceFilingList:
    @patch.object(EdgarService, "_get")
    def test_get_filing_list(self, mock_get, service):
        mock_get.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K"],
                    "filingDate": ["2024-02-28", "2024-05-01", "2024-08-15"],
                    "accessionNumber": ["0001193125-24-012345", "0001193125-24-067890", "0001193125-24-111111"],
                    "primaryDocument": ["doc.htm", "doc.htm", "doc.htm"],
                }
            }
        }
        filings = service.get_filing_list("0001043604", "10-K", limit=5)
        assert len(filings) == 1
        assert filings[0]["form"] == "10-K"
        assert filings[0]["filingDate"] == "2024-02-28"

    @patch.object(EdgarService, "_get")
    def test_get_filing_list_empty(self, mock_get, service):
        mock_get.return_value = {}
        filings = service.get_filing_list("0000000000", "10-K")
        assert filings == []


class TestEdgarServiceIngest:
    @patch.object(EdgarService, "download_filing", return_value="Funds from operations (FFO) per share was $6.15 for the quarter.")
    @patch.object(EdgarService, "get_filing_list", return_value=[
        {"filingDate": "2024-02-28", "accessionNumber": "0001193125-24-012345", "primaryDocument": "doc.htm"}
    ])
    def test_ingest_filing_success(self, mock_list, mock_download, service):
        filing = service.ingest_filing("PLD", "10-K", cik="0001093557")
        assert filing is not None
        assert filing.reit_ticker == "PLD"
        assert filing.status == FilingStatus.PARSED
        assert filing.get_extracted_metric("ffo_per_share") == pytest.approx(6.15)

    def test_ingest_filing_no_cik(self, service):
        with patch.object(service, "lookup_cik", return_value=None):
            filing = service.ingest_filing("FAKE")
            assert filing is None


class TestEdgarServiceThrottle:
    def test_throttle_called(self, service):
        import time
        before = time.time()
        service._throttle()
        after = time.time()
        # With rate_limit=0.0, throttle should be nearly instant
        assert after - before < 0.1

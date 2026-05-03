"""
EDGAR Service — SEC EDGAR filing ingestion for REITs.

Fetches 10-K, 10-Q, 8-K filings via the EDGAR Full-Text Search API,
extracts text content, and parses key financial metrics.

Rate limit: 10 requests/second per SEC requirements.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.models.sec_filing import FilingStatus, FilingType, SECFiling

logger = logging.getLogger(__name__)

EDGAR_BASE_URL = "https://www.sec.gov"
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_DATA_URL = "https://data.sec.gov"

# CIK lookup for seed REITs
REIT_CIK_MAP: Dict[str, str] = {
    "O": "0001043604",
    "AMT": "0001067983",
    "PLD": "0001093557",
    "SPG": "0000862009",
    "EQIX": "0001066196",
    "PSB": "0000908535",
    "AVB": "0000908535",
    "WELL": "0001393818",
    "DLR": "0001103982",
    "VICI": "0001701605",
    "CCI": "0001022079",
    "AMH": "0001526524",
}

REIT_CIK_MAP["AVB"] = "0000763522"
REIT_CIK_MAP["PSB"] = "0000720526"


class EdgarService:
    """Service for fetching and parsing SEC EDGAR filings."""

    def __init__(
        self,
        user_agent: str = "Scope Sentinel research@example.com",
        rate_limit: float = 0.1,
    ) -> None:
        self.user_agent = user_agent
        self.rate_limit = rate_limit
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
        })
        self._last_request_time: float = 0.0

    def _throttle(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a throttled GET request to EDGAR."""
        self._throttle()
        try:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()
            if "application/json" in response.headers.get("Content-Type", ""):
                return response.json()
            return {"content": response.text, "status_code": response.status_code}
        except requests.RequestException as e:
            logger.error(f"EDGAR request failed for {url}: {e}")
            return None

    def lookup_cik(self, ticker: str) -> Optional[str]:
        """Look up CIK number for a ticker symbol."""
        ticker = ticker.strip().upper()
        if ticker in REIT_CIK_MAP:
            return REIT_CIK_MAP[ticker]

        url = f"{EDGAR_DATA_URL}/submissions/CIK0000000000.json"
        # Company facts lookup
        url = f"{EDGAR_DATA_URL}/cgi-bin/browse-edgar"
        params = {"action": "getcompany", "company": ticker, "type": "", "dateb": "", "owner": "include", "count": 1}
        result = self._get(url, params)
        if result and "content" in result:
            match = re.search(r'CIK=(\d{10})', str(result.get("content", "")))
            if match:
                cik = match.group(1)
                REIT_CIK_MAP[ticker] = cik
                return cik
        return None

    def search_filings(
        self,
        ticker: str,
        form_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        """Search for filings using EDGAR Full-Text Search API."""
        cik = self.lookup_cik(ticker)
        if not cik:
            logger.warning(f"No CIK found for ticker {ticker}")
            return []

        query = f'cik:"{cik.strip("0")}"'
        if form_type:
            query += f' AND form:"{form_type}"'

        params = {
            "q": query,
            "dateRange": "custom",
            "startdt": start_date or "2020-01-01",
            "enddt": end_date or "2025-12-31",
            "forms": form_type or "",
            "num": limit,
        }
        result = self._get(EDGAR_SEARCH_URL, params)
        if result and "hits" in result:
            return result["hits"]["hits"] if isinstance(result["hits"], dict) else result.get("hits", [])
        return []

    def get_filing_list(
        self,
        cik: str,
        filing_type: str = "10-K",
        limit: int = 5,
    ) -> List[Dict]:
        """Get recent filings for a CIK from the submissions API."""
        padded_cik = cik.zfill(10)
        url = f"{EDGAR_DATA_URL}/submissions/CIK{padded_cik}.json"
        result = self._get(url)
        if not result or "filings" not in result:
            return []

        recent = result["filings"].get("recent", {})
        filings = []
        for i, form in enumerate(recent.get("form", [])):
            if i >= limit:
                break
            if filing_type and form != filing_type:
                continue
            filing = {
                "form": form,
                "filingDate": recent.get("filingDate", [])[i] if recent.get("filingDate") else "",
                "accessionNumber": recent.get("accessionNumber", [])[i] if recent.get("accessionNumber") else "",
                "primaryDocument": recent.get("primaryDocument", [])[i] if recent.get("primaryDocument") else "",
            }
            filings.append(filing)
        return filings

    def download_filing(self, cik: str, accession: str, primary_doc: str) -> Optional[str]:
        """Download filing document text."""
        padded_cik = cik.zfill(10)
        clean_accession = accession.replace("-", "")
        url = f"{EDGAR_DATA_URL}/Archives/edgar/data/{padded_cik}/{clean_accession}/{primary_doc}"
        result = self._get(url)
        if result and "content" in result:
            return result["content"]
        return None

    def extract_financials(self, text: str) -> Dict[str, float]:
        """Extract key financial metrics from filing text using regex patterns."""
        metrics: Dict[str, float] = {}

        # FFO per share patterns
        ffo_patterns = [
            r"FFO\s+(?:per\s+share|/share)?\s*(?:was|of)?\s*\$?([\d,.]+)",
            r"funds?\s+from\s+operations.*?per\s+share.*?\$?([\d,.]+)",
            r"FFO.*?\$([\d,.]+)\s*(?:per|/) share",
        ]
        for pattern in ffo_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    metrics["ffo_per_share"] = float(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    pass

        # NOI patterns
        noi_patterns = [
            r"NOI\s*(?:was|of|:)?\s*\$?([\d,.]+)\s*(?:million|billion)",
            r"net\s+operating\s+income.*?\$?([\d,.]+)",
        ]
        for pattern in noi_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1).replace(",", ""))
                    if "billion" in match.group(0).lower():
                        val *= 1000
                    metrics["noi"] = val
                    break
                except ValueError:
                    pass

        # Revenue patterns
        rev_patterns = [
            r"total\s+revenue.*?\$?([\d,.]+)\s*(?:million|billion)",
            r"revenue\s*(?:was|of)?\s*\$?([\d,.]+)",
        ]
        for pattern in rev_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1).replace(",", ""))
                    if "billion" in match.group(0).lower():
                        val *= 1000
                    metrics["total_revenue"] = val
                    break
                except ValueError:
                    pass

        # Occupancy patterns
        occ_patterns = [
            r"occupancy\s*(?:rate)?\s*(?:of|was|:)?\s*([\d.]+)\s*%",
            r"leased\s*(?:percentage|rate)?\s*(?:of)?\s*([\d.]+)\s*%",
        ]
        for pattern in occ_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    metrics["occupancy_rate"] = float(match.group(1)) / 100.0
                    break
                except ValueError:
                    pass

        # Dividend patterns
        div_patterns = [
            r"dividend\s*(?:per\s+share)?\s*(?:of|was|:|=\s*)\s*\$?([\d,.]+)",
            r"per\s+share.*?dividend.*?\$([\d,.]+)",
        ]
        for pattern in div_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    metrics["dividend_per_share"] = float(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    pass

        # Debt/EBITDA
        debt_patterns = [
            r"(?:net\s+)?debt\s*(?:to)?\s*EBITDA\s*(?:of|was|:|ratio)?\s*([\d.]+)",
            r"debt.*?EBITDA.*?([\d.]+)x",
        ]
        for pattern in debt_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    metrics["debt_to_ebitda"] = float(match.group(1))
                    break
                except ValueError:
                    pass

        return metrics

    def ingest_filing(
        self,
        reit_ticker: str,
        form_type: str = "10-K",
        cik: Optional[str] = None,
    ) -> Optional[SECFiling]:
        """Full ingestion pipeline: lookup → fetch list → download → extract → parse."""
        if not cik:
            cik = self.lookup_cik(reit_ticker)
        if not cik:
            logger.error(f"Cannot ingest filing for {reit_ticker}: no CIK found")
            return None

        filing_type = FilingType(form_type)
        filings = self.get_filing_list(cik, form_type, limit=1)

        if not filings:
            logger.warning(f"No {form_type} filings found for {reit_ticker}")
            return None

        latest = filings[0]
        filing_date = latest.get("filingDate", "")
        accession = latest.get("accessionNumber", "")
        primary_doc = latest.get("primaryDocument", "")

        filing_id = SECFiling.build_filing_id(reit_ticker, form_type, filing_date)
        filing = SECFiling(
            filing_id=filing_id,
            reit_ticker=reit_ticker,
            cik=cik,
            form_type=filing_type,
            filing_date=filing_date,
        )

        # Download
        text = self.download_filing(cik, accession, primary_doc)
        if not text:
            filing.mark_failed("Failed to download filing document")
            return filing

        filing.mark_downloaded(
            url=f"{EDGAR_DATA_URL}/Archives/edgar/data/{cik.zfill(10)}/{accession.replace('-', '')}/{primary_doc}",
            size=len(text),
        )

        # Extract
        filing.mark_extracted(text[:8000])  # Truncate for storage

        # Parse financials
        metrics = self.extract_financials(text)
        filing.mark_parsed(metrics)

        logger.info(f"Ingested {form_type} for {reit_ticker}: {len(metrics)} metrics extracted")
        return filing

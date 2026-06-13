"""
SEC Ingestion Lambda Handler — EventBridge → check new EDGAR filings → ingest.

Triggered by EventBridge cron (daily at 6 AM ET) or manual invocation.
"""

import json
import logging
import os
from datetime import datetime

import boto3
import requests

from scope_core import success_response, write_object_to_s3

logger = logging.getLogger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_DATA_URL = "https://data.sec.gov"

REIT_TICKERS = ["O", "AMT", "PLD", "SPG", "EQIX", "PSB", "AVB", "WELL", "DLR", "VICI", "CCI", "AMH"]


def check_new_filings(ticker: str, user_agent: str) -> list:
    """Check for recent filings on EDGAR for a given REIT ticker."""
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    try:
        # Use EDGAR full-text search for recent filings
        params = {
            "q": f'ticker:"{ticker}"',
            "forms": "10-K,10-Q,8-K",
            "dateRange": "custom",
            "startdt": (datetime.utcnow()).strftime("%Y-%m-%d"),
            "enddt": (datetime.utcnow()).strftime("%Y-%m-%d"),
            "num": 10,
        }
        response = session.get(EDGAR_SEARCH_URL, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data.get("hits", {}).get("hits", []) if isinstance(data.get("hits"), dict) else data.get("hits", [])
        return []
    except Exception as e:
        logger.error(f"Error checking filings for {ticker}: {e}")
        return []


def handler(event, context):
    """AWS Lambda entry point for SEC filing ingestion.

    EventBridge cron event or manual invocation:
    {
        "tickers": ["O", "PLD"],   // optional, defaults to all 12
        "check_days": 1             // optional
    }
    """
    logger.info(f"SEC Ingestion Lambda triggered: {json.dumps(event)[:500]}")

    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "Scope Sentinel research@example.com")
    tickers = event.get("tickers", REIT_TICKERS)
    raw_bucket = os.environ.get("RAW_BUCKET", "scope-sentinel-raw")

    s3 = boto3.client("s3")
    new_filings = []
    processed = 0

    for ticker in tickers:
        try:
            filings = check_new_filings(ticker, user_agent)
            for filing in filings:
                filing_data = filing.get("_source", {})
                form_type = filing_data.get("form", "Unknown")
                filing_date = filing_data.get("file_date", "")
                accession = filing_data.get("accession_no", "")

                if form_type in ("10-K", "10-Q", "8-K"):
                    # Write to S3 for downstream processing
                    s3_key = f"sec_filings/raw/{ticker}/{form_type}/{accession}.json"
                    write_object_to_s3(
                        s3,
                        bucket=raw_bucket,
                        key=s3_key,
                        body=json.dumps(filing_data),
                        content_type="application/json",
                    )
                    new_filings.append({
                        "ticker": ticker,
                        "form_type": form_type,
                        "filing_date": filing_date,
                        "accession": accession,
                        "s3_key": s3_key,
                    })
                    processed += 1

        except Exception as e:
            logger.error(f"Error processing ticker {ticker}: {e}")

    result = {
        "status": "completed",
        "tickers_checked": len(tickers),
        "new_filings": new_filings,
        "total_processed": processed,
        "timestamp": datetime.utcnow().isoformat(),
    }

    return success_response(result)

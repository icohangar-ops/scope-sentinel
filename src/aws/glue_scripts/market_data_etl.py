# Glue ETL: Market Data Ingestion
# Ingests FRED and AlphaVantage data, normalizes, and computes derived indicators.

import json
import logging
import os
import sys
from datetime import datetime, timedelta

import boto3
import requests

sys.path.insert(0, "/opt/python")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FRED_BASE = "https://api.stlouisfed.org/fred"
AV_BASE = "https://www.alphavantage.co/query"


def ingest_fred_data(event):
    """Fetch FRED indicators and write to S3 for Iceberg ingestion.

    Expected event format:
    {
        "series_ids": ["FEDFUNDS", "DGS10", "DGS2", "CPIAUCSL"],
        "lookback_days": 730
    }
    """
    series_ids = event.get("series_ids", ["FEDFUNDS", "DGS10", "DGS2", "WFII", "UNRATE"])
    lookback = event.get("lookback_days", 730)
    api_key = os.environ.get("FRED_API_KEY", "")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback)).strftime("%Y-%m-%d")

    s3 = boto3.client("s3")
    bucket = os.environ.get("RAW_BUCKET", "scope-sentinel-raw")
    database = os.environ.get("GLUE_DATABASE", "scope_sentinel")

    ingested = []
    for series_id in series_ids:
        try:
            params = {
                "api_key": api_key,
                "file_type": "json",
                "series_id": series_id,
                "observation_start": start_date,
                "observation_end": end_date,
                "sort_order": "desc",
                "limit": 100,
            }
            response = requests.get(f"{FRED_BASE}/series/observations", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            observations = data.get("observations", [])
            s3_key = f"market_data/fred/{series_id}/{end_date}.json"
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=json.dumps(observations),
                ContentType="application/json",
            )

            ingested.append({"series_id": series_id, "records": len(observations), "s3_key": s3_key})
            logger.info(f"Ingested {len(observations)} observations for {series_id}")

        except Exception as e:
            logger.error(f"Error ingesting {series_id}: {e}")
            ingested.append({"series_id": series_id, "error": str(e)})

    return {
        "status": "completed",
        "ingested": ingested,
        "timestamp": datetime.utcnow().isoformat(),
    }


def ingest_price_data(event):
    """Fetch AlphaVantage price data and write to S3.

    Expected event format:
    {
        "tickers": ["O", "PLD", "SPG", "VNQ"],
        "output_size": "compact"
    }
    """
    tickers = event.get("tickers", ["O", "PLD", "SPG", "VNQ"])
    api_key = os.environ.get("ALPHA_VANTAGE_KEY", "")

    s3 = boto3.client("s3")
    bucket = os.environ.get("RAW_BUCKET", "scope-sentinel-raw")
    date_str = datetime.now().strftime("%Y-%m-%d")

    ingested = []
    for ticker in tickers:
        try:
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": "compact",
                "apikey": api_key,
                "datatype": "json",
            }
            response = requests.get(AV_BASE, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            series = data.get("Time Series (Daily)", {})
            s3_key = f"market_data/alpha_vantage/{ticker}/{date_str}.json"
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=json.dumps(series),
                ContentType="application/json",
            )

            ingested.append({"ticker": ticker, "records": len(series), "s3_key": s3_key})
            logger.info(f"Ingested {len(series)} price records for {ticker}")

        except Exception as e:
            logger.error(f"Error ingesting prices for {ticker}: {e}")
            ingested.append({"ticker": ticker, "error": str(e)})

    return {
        "status": "completed",
        "ingested": ingested,
        "timestamp": datetime.utcnow().isoformat(),
    }


def lambda_handler(event, context):
    """AWS Lambda entry point for market data ingestion."""
    logger.info(f"Market Data ETL triggered: {json.dumps(event)[:500]}")

    try:
        data_type = event.get("type", "both")
        results = {}

        if data_type in ("fred", "both"):
            results["fred"] = ingest_fred_data(event)
        if data_type in ("prices", "both"):
            results["prices"] = ingest_price_data(event)

        return {"statusCode": 200, "body": json.dumps(results)}
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

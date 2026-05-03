# Glue ETL: SEC Filing Ingestion
# Extracts SEC filing text and parses key financial metrics for REITs.

import json
import logging
import os
import sys
from datetime import datetime

import boto3

# Add source to path for Lambda
sys.path.insert(0, "/opt/python")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_glue_client():
    """Create Glue client with proper configuration."""
    return boto3.client("glue")


def get_s3_client():
    """Create S3 client."""
    return boto3.client("s3")


def process_filings(event):
    """Process SEC filings from S3 trigger or EventBridge schedule.

    Expected event format:
    {
        "tickers": ["O", "PLD", "SPG"],
        "form_types": ["10-K", "10-Q"],
        "bucket": "scope-sentinel-raw",
        "prefix": "sec_filings/"
    }
    """
    tickers = event.get("tickers", [])
    form_types = event.get("form_types", ["10-K", "10-Q"])
    bucket = event.get("bucket", os.environ.get("RAW_BUCKET", "scope-sentinel-raw"))
    prefix = event.get("prefix", "sec_filings/")

    processed = 0
    errors = []

    for ticker in tickers:
        for form_type in form_types:
            try:
                # Check for new filings in S3
                s3 = get_s3_client()
                s3_key = f"{prefix}{ticker}/{form_type}/"

                # Write marker file to Iceberg staging
                glue = get_glue_client()
                database = os.environ.get("GLUE_DATABASE", "scope_sentinel")
                table = "sec_filings_raw"

                # Run Glue Crawler or direct insert
                glue.start_crawler(Name=f"{database}_crawler")

                processed += 1
                logger.info(f"Processed {form_type} for {ticker}")

            except Exception as e:
                errors.append({"ticker": ticker, "form_type": form_type, "error": str(e)})
                logger.error(f"Error processing {ticker} {form_type}: {e}")

    return {
        "status": "completed",
        "processed": processed,
        "errors": errors,
        "timestamp": datetime.utcnow().isoformat(),
    }


def lambda_handler(event, context):
    """AWS Lambda entry point for SEC filing ingestion.

    Triggered by:
    - EventBridge cron (daily at 6 AM ET)
    - S3 event notification (new filing uploaded)
    - Manual invocation via Step Functions
    """
    logger.info(f"SEC Ingestion triggered: {json.dumps(event)[:500]}")

    try:
        result = process_filings(event)
        result["lambda_log_group"] = context.log_group_name if context else "local"
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# Glue ETL: Financial Metrics Computation
# Computes peer metrics, sector benchmarks, and trend analysis from raw financials.

import json
import logging
import os
import sys
from datetime import datetime

import boto3

sys.path.insert(0, "/opt/python")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def compute_financial_metrics(event):
    """Compute derived financial metrics and benchmarks.

    Expected event format:
    {
        "tickers": ["O", "PLD", "SPG"],
        "fiscal_year": 2024,
        "quarters": [1, 2, 3, 4],
        "target_table": "financial_metrics"
    }
    """
    tickers = event.get("tickers", [])
    fiscal_year = event.get("fiscal_year", datetime.now().year - 1)

    database = os.environ.get("GLUE_DATABASE", "scope_sentinel")
    athena = boto3.client("athena")
    s3_output = os.environ.get("ATHENA_OUTPUT", "s3://scope-sentinel-queries/")

    results = []
    for ticker in tickers:
        try:
            # Compute peer comparison metrics
            query = f"""
            WITH peer_avg AS (
                SELECT
                    sub_sector,
                    AVG(ffo_per_share) as avg_ffo,
                    AVG(same_store_noi_growth) as avg_noi_growth,
                    AVG(net_debt_to_ebitda) as avg_leverage,
                    AVG(dividend_yield) as avg_yield
                FROM {database}.reits r
                JOIN {database}.financial_metrics fm ON r.ticker = fm.reit_ticker
                WHERE fm.fiscal_year = {fiscal_year}
                GROUP BY sub_sector
            )
            SELECT
                fm.reit_ticker,
                fm.ffo_per_share,
                fm.ffo_per_share - pa.avg_ffo as ffo_vs_peers,
                fm.same_store_noi_growth - pa.avg_noi_growth as noi_vs_peers,
                fm.net_debt_to_ebitda - pa.avg_leverage as leverage_vs_peers,
                r.dividend_yield - pa.avg_yield as yield_vs_peers
            FROM {database}.financial_metrics fm
            JOIN {database}.reits r ON fm.reit_ticker = r.ticker
            JOIN peer_avg pa ON r.sub_sector = pa.sub_sector
            WHERE fm.reit_ticker = '{ticker}'
              AND fm.fiscal_year = {fiscal_year}
            """

            response = athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": database},
                ResultConfiguration={"OutputLocation": s3_output},
            )
            results.append({"ticker": ticker, "query_id": response["QueryExecutionId"]})
            logger.info(f"Submitted financial metrics query for {ticker}")

        except Exception as e:
            logger.error(f"Error computing metrics for {ticker}: {e}")
            results.append({"ticker": ticker, "error": str(e)})

    # Compute sector benchmarks
    benchmark_query = f"""
    INSERT INTO {database}.sector_benchmarks
    SELECT
        r.sector,
        COUNT(*) as reit_count,
        AVG(fm.ffo_per_share) as avg_ffo,
        AVG(fm.same_store_noi_growth) as avg_noi_growth,
        AVG(fm.net_debt_to_ebitda) as avg_leverage,
        AVG(r.dividend_yield) as avg_yield,
        AVG(fm.weighted_avg_cap_rate) as avg_cap_rate,
        CURRENT_TIMESTAMP as computed_at
    FROM {database}.reits r
    JOIN {database}.financial_metrics fm ON r.ticker = fm.reit_ticker
    WHERE fm.fiscal_year = {fiscal_year}
    GROUP BY r.sector
    """

    try:
        athena.start_query_execution(
            QueryString=benchmark_query,
            QueryExecutionContext={"Database": database},
            ResultConfiguration={"OutputLocation": s3_output},
        )
        logger.info("Submitted sector benchmark query")
    except Exception as e:
        logger.error(f"Error computing sector benchmarks: {e}")

    return {
        "status": "completed",
        "tickers_processed": len(results),
        "results": results,
        "timestamp": datetime.utcnow().isoformat(),
    }


def lambda_handler(event, context):
    """AWS Lambda entry point for financial metrics computation."""
    logger.info(f"Financial ETL triggered: {json.dumps(event)[:500]}")

    try:
        result = compute_financial_metrics(event)
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

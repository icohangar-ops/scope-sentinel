"""
Analysis Lambda Handler — Step Functions → compute signals → Bedrock → reports.

Orchestrated by Step Functions state machine:
1. Ingest latest data (financials, prices, macro)
2. Compute component scores
3. Call Bedrock for AI analysis
4. Generate final signals and write to Iceberg
"""

import json
import logging
import os
from datetime import datetime

import boto3

logger = logging.getLogger(__name__)


def compute_signal_scores(event):
    """Compute composite Sentinel scores for given tickers.

    Expected event:
    {
        "tickers": ["O", "PLD", "SPG"],
        "fiscal_year": 2024
    }
    """
    tickers = event.get("tickers", [])
    athena = boto3.client("athena")
    database = os.environ.get("GLUE_DATABASE", "scope_sentinel")
    s3_output = os.environ.get("ATHENA_OUTPUT", "s3://scope-sentinel-queries/")

    signals = []
    for ticker in tickers:
        try:
            # Query for latest financial data
            query = f"""
            SELECT
                r.ticker, r.name, r.sector, r.sub_sector,
                r.dividend_yield, r.payout_ratio,
                fm.ffo_per_share, fm.affo_per_share,
                fm.same_store_noi_growth, fm.ffo_growth_yoy,
                fm.net_debt_to_ebitda, fm.interest_coverage,
                fm.weighted_avg_cap_rate, fm.dividend_growth_yoy
            FROM {database}.reits r
            LEFT JOIN {database}.financial_metrics fm
              ON r.ticker = fm.reit_ticker
              AND fm.fiscal_year = (SELECT MAX(fiscal_year) FROM {database}.financial_metrics WHERE reit_ticker = '{ticker}')
              AND fm.quarter = (SELECT MAX(quarter) FROM {database}.financial_metrics WHERE reit_ticker = '{ticker}' AND fiscal_year = fm.fiscal_year)
            WHERE r.ticker = '{ticker}'
            """
            response = athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": database},
                ResultConfiguration={"OutputLocation": f"{s3_output}signals/"},
            )
            signals.append({
                "ticker": ticker,
                "query_id": response["QueryExecutionId"],
                "status": "submitted",
            })
        except Exception as e:
            logger.error(f"Error computing signal for {ticker}: {e}")
            signals.append({"ticker": ticker, "status": "error", "error": str(e)})

    return signals


def invoke_bedrock_analysis(ticker: str, signal_data: dict):
    """Invoke Bedrock Converse API for AI analysis of a REIT."""
    bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    prompt = f"""Analyze REIT {ticker} based on:
- Sentinel Score: {signal_data.get('sentinel_score', 'N/A')}
- FFO/Share: ${signal_data.get('ffo_per_share', 'N/A')}
- NOI Growth: {signal_data.get('noi_growth', 'N/A')}%
- Dividend Yield: {signal_data.get('dividend_yield', 'N/A')}%
- Debt/EBITDA: {signal_data.get('leverage', 'N/A')}x

Provide concise investment recommendation (2-3 paragraphs)."""

    try:
        response = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            system=[{"text": "You are a senior REIT analyst. Be concise and data-driven."}],
            inferenceConfig={"maxTokens": 800, "temperature": 0.3},
        )
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        return "".join(cb.get("text", "") for cb in content_blocks)
    except Exception as e:
        logger.error(f"Bedrock analysis failed for {ticker}: {e}")
        return f"Analysis unavailable: {str(e)}"


def write_signals_to_iceberg(signals: list):
    """Write computed signals to Iceberg table via Athena."""
    athena = boto3.client("athena")
    database = os.environ.get("GLUE_DATABASE", "scope_sentinel")
    s3_output = os.environ.get("ATHENA_OUTPUT", "s3://scope-sentinel-queries/")

    for signal in signals:
        if signal.get("status") != "computed":
            continue
        try:
            ticker = signal["ticker"]
            query = f"""
            INSERT INTO {database}.reit_signals
            VALUES (
                '{ticker}_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}',
                '{ticker}',
                TIMESTAMP '{datetime.utcnow().isoformat()}',
                {signal.get('sentinel_score', 50)},
                {signal.get('fundamental_score', 50)},
                {signal.get('valuation_score', 50)},
                {signal.get('momentum_score', 50)},
                {signal.get('macro_score', 50)},
                {signal.get('sentiment_score', 50)},
                '{signal.get("signal_rating", "Hold")}',
                '{signal.get("ai_analysis", "")[:4000].replace("'", "''")}',
                '{json.dumps(signal.get("key_risks", [])).replace("'", "''")}',
                '{json.dumps(signal.get("key_opportunities", [])).replace("'", "''")}',
                {signal.get("confidence_score", 0.5)}
            )
            """
            athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": database},
                ResultConfiguration={"OutputLocation": f"{s3_output}signals/write/"},
            )
        except Exception as e:
            logger.error(f"Error writing signal for {signal.get('ticker')}: {e}")


def handler(event, context):
    """AWS Lambda entry point for analysis pipeline.

    Step Functions passes:
    {
        "step": "compute_scores" | "bedrock_analysis" | "write_signals",
        "tickers": ["O", "PLD"],
        "signals": [...]  // for bedrock_analysis or write_signals steps
    }
    """
    logger.info(f"Analysis Lambda triggered: {json.dumps(event)[:500]}")

    step = event.get("step", "compute_scores")

    if step == "compute_scores":
        signals = compute_signal_scores(event)
        return {"statusCode": 200, "body": json.dumps({"step": step, "signals": signals})}

    elif step == "bedrock_analysis":
        signals = event.get("signals", [])
        for signal in signals:
            ticker = signal.get("ticker", "")
            analysis = invoke_bedrock_analysis(ticker, signal)
            signal["ai_analysis"] = analysis
            signal["status"] = "analyzed"
        return {"statusCode": 200, "body": json.dumps({"step": step, "signals": signals})}

    elif step == "write_signals":
        write_signals_to_iceberg(event.get("signals", []))
        return {"statusCode": 200, "body": json.dumps({"step": step, "status": "completed"})}

    return {"statusCode": 400, "body": json.dumps({"error": f"Unknown step: {step}"})}

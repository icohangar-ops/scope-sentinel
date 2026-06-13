"""
Analysis Lambda Handler — Step Functions → compute signals → Bedrock → reports.

Orchestrated by Step Functions state machine:
1. Ingest latest data (financials, prices, macro)
2. Compute component scores
3. Call Bedrock for AI analysis
4. Generate final signals and write to Iceberg
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime

import boto3

from cubiczan_resilience import FileIdempotencyStore
from scope_core import (
    SafeAthenaClient,
    error_response,
    success_response,
    validate_in_allowlist,
)

logger = logging.getLogger(__name__)

# Idempotency store for signal writes. Backed by a file under /tmp (the only
# writable, warm-reusable path in a Lambda container) so repeated invocations
# within a warm container short-circuit duplicate INSERTs even before Athena
# is consulted. The deterministic signal_id is the idempotency key.
_IDEMPOTENCY_PATH = os.environ.get("SIGNAL_IDEMPOTENCY_PATH", "/tmp/scope-sentinel-signals.json")
_signal_idempotency = FileIdempotencyStore(_IDEMPOTENCY_PATH)

# Terminal Athena query states.
_ATHENA_TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED")

# Allowlist of tradeable REIT tickers. Any ticker interpolated into Athena SQL
# MUST be validated against this set to prevent SQL injection via the Lambda
# event payload. Kept in sync with sec_ingestion_handler.REIT_TICKERS.
ALLOWED_TICKERS = frozenset(
    ["O", "AMT", "PLD", "SPG", "EQIX", "PSB", "AVB", "WELL", "DLR", "VICI", "CCI", "AMH"]
)


def _validate_ticker(ticker) -> str:
    """Validate a ticker against the allowlist before SQL interpolation.

    Delegates to scope_core.validate_in_allowlist (the shared SQL-injection
    defense); ALLOWED_TICKERS is this repo's domain allowlist. Raises
    IdentifierError (a ValueError subclass) for any value outside the set.
    """
    return validate_in_allowlist(ticker, ALLOWED_TICKERS, field="ticker")


def _sql_str(value, max_len: int = 4000) -> str:
    """Escape an arbitrary value for safe insertion as a single-quoted SQL literal."""
    text = str(value)[:max_len]
    return text.replace("'", "''")


def _sql_num(value, default):
    """Coerce a value to a numeric SQL literal, falling back to default.

    Prevents injection through fields that are interpolated without quotes.
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = float(default)
    if num != num or num in (float("inf"), float("-inf")):  # NaN/inf guard
        num = float(default)
    return repr(num)


def compute_signal_scores(event):
    """Compute composite Sentinel scores for given tickers.

    Expected event:
    {
        "tickers": ["O", "PLD", "SPG"],
        "fiscal_year": 2024
    }
    """
    tickers = event.get("tickers", [])
    database = os.environ.get("GLUE_DATABASE", "scope_sentinel")
    s3_output = os.environ.get("ATHENA_OUTPUT", "s3://scope-sentinel-queries/")
    client = SafeAthenaClient(
        boto3.client("athena"),
        database=database,
        output_location=f"{s3_output}signals/",
    )

    signals = []
    for ticker in tickers:
        try:
            ticker = _validate_ticker(ticker)
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
            query_id = client.start(query)
            signals.append({
                "ticker": ticker,
                "query_id": query_id,
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


def _deterministic_signal_id(ticker: str, signal: dict) -> str:
    """Build a deterministic signal_id from ticker + fiscal period.

    The id is a function of the *data the signal describes* (ticker + fiscal
    year/quarter), NOT wall-clock time, so re-running the pipeline for the same
    fiscal period produces the same id. This is what makes the downstream
    INSERT idempotent: a replay collides with the prior row instead of
    appending a new timestamped duplicate.
    """
    fiscal_year = signal.get("fiscal_year", "")
    quarter = signal.get("quarter", "")
    digest = hashlib.sha256(
        f"{ticker}|{fiscal_year}|{quarter}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{ticker}_{digest}"


def _wait_for_query(athena, query_execution_id: str, timeout_s: float = 60.0) -> str:
    """Poll GetQueryExecution until the query reaches a terminal state.

    Returns the terminal state string (SUCCEEDED/FAILED/CANCELLED). Without
    this poll the writer fires-and-forgets, so a FAILED insert would be
    silently lost and a replay could not tell whether the row landed.
    """
    deadline = time.time() + timeout_s
    delay = 0.5
    while True:
        resp = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = resp["QueryExecution"]["Status"]["State"]
        if state in _ATHENA_TERMINAL:
            return state
        if time.time() >= deadline:
            return state
        time.sleep(delay)
        delay = min(delay * 2, 5.0)


def write_signals_to_iceberg(signals: list):
    """Write computed signals to Iceberg table via Athena (idempotent)."""
    athena = boto3.client("athena")
    database = os.environ.get("GLUE_DATABASE", "scope_sentinel")
    s3_output = os.environ.get("ATHENA_OUTPUT", "s3://scope-sentinel-queries/")
    client = SafeAthenaClient(
        athena,
        database=database,
        output_location=f"{s3_output}signals/write/",
    )

    for signal in signals:
        if signal.get("status") != "computed":
            continue
        try:
            ticker = _validate_ticker(signal["ticker"])
            signal_id = _deterministic_signal_id(ticker, signal)

            # Warm-container short-circuit: if this exact signal_id was already
            # written in this container, skip re-issuing the INSERT entirely.
            if _signal_idempotency.already_done(signal_id):
                logger.info(f"Signal {signal_id} already written; skipping")
                continue

            # INSERT guarded by NOT EXISTS so a replay (e.g. Step Functions
            # retry, or a new container with no local idempotency state) does
            # not create a duplicate row for the same deterministic signal_id.
            query = f"""
            INSERT INTO {database}.reit_signals
            SELECT
                '{signal_id}',
                '{ticker}',
                TIMESTAMP '{datetime.utcnow().isoformat()}',
                {_sql_num(signal.get('sentinel_score'), 50)},
                {_sql_num(signal.get('fundamental_score'), 50)},
                {_sql_num(signal.get('valuation_score'), 50)},
                {_sql_num(signal.get('momentum_score'), 50)},
                {_sql_num(signal.get('macro_score'), 50)},
                {_sql_num(signal.get('sentiment_score'), 50)},
                '{_sql_str(signal.get("signal_rating", "Hold"))}',
                '{_sql_str(signal.get("ai_analysis", ""))}',
                '{_sql_str(json.dumps(signal.get("key_risks", [])))}',
                '{_sql_str(json.dumps(signal.get("key_opportunities", [])))}',
                {_sql_num(signal.get("confidence_score"), 0.5)}
            WHERE NOT EXISTS (
                SELECT 1 FROM {database}.reit_signals WHERE signal_id = '{signal_id}'
            )
            """
            query_id = client.start(query)

            # Poll to a terminal state instead of fire-and-forget.
            state = _wait_for_query(athena, query_id)
            if state == "SUCCEEDED":
                _signal_idempotency.mark_done(signal_id, query_id)
            else:
                logger.error(
                    f"Signal write for {signal_id} ended in state {state}; not marking done"
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
        return success_response({"step": step, "signals": signals})

    elif step == "bedrock_analysis":
        signals = event.get("signals", [])
        for signal in signals:
            ticker = signal.get("ticker", "")
            analysis = invoke_bedrock_analysis(ticker, signal)
            signal["ai_analysis"] = analysis
            signal["status"] = "analyzed"
        return success_response({"step": step, "signals": signals})

    elif step == "write_signals":
        write_signals_to_iceberg(event.get("signals", []))
        return success_response({"step": step, "status": "completed"})

    return error_response(f"Unknown step: {step}", status_code=400)

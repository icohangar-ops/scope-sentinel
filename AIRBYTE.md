# Airbyte Agents Integration — Scope.Sentinel

This document describes how [Airbyte Agents](https://docs.airbyte.com/ai-agents) can replace the custom Lambda ingestion layer for SEC EDGAR, AlphaVantage, and FRED data with managed connectors.

---

## Overview

Scope.Sentinel ingests REIT analytics data via SEC EDGAR, AlphaVantage, and FRED through custom Lambda handlers. Airbyte Agents can replace these with declarative source configurations and incremental syncs.

**Integration options:**
- **[MCP](https://docs.airbyte.com/ai-agents/interfaces/mcp)** — Remote MCP server for ad-hoc REIT data queries.
- **[SDK](https://docs.airbyte.com/ai-agents/interfaces/sdk)** — Python library for replacing Lambda-based ingestion.
- **[API](https://docs.airbyte.com/ai-agents/interfaces/sdk)** — REST for IaC orchestration.

---

## Integration Points

### 1. Replace Lambda Ingestion with Airbyte Sources

| Current Service | File | Data | Airbyte Alternative |
|----------------|------|------|-------------------|
| `EdgarService` | `src/services/edgar_service.py` | SEC 10-K, 10-Q, 8-K filings for 12 seed REITs | Airbyte SEC EDGAR (custom) or generic HTTP source |
| `PricingService` | `src/services/pricing_service.py` | AlphaVantage daily/weekly prices for REITs + ETFs | Airbyte AlphaVantage source |
| `FredService` | `src/services/fred_service.py` | Fed funds, treasuries, CPI, unemployment, housing | Airbyte FRED source |

### 2. Airbyte → Iceberg Pipeline

```
External Sources
  ├── SEC EDGAR ───→ Airbyte Source ──→ S3 ──→ Iceberg: sec_filings_raw
  ├── AlphaVantage ──→ Airbyte Source ──→ S3 ──→ Iceberg: financial_metrics  
  └── FRED ──────────→ Airbyte Source ──→ S3 ──→ Iceberg: market_indicators
                                                  │
                                                  ▼
                                          Glue ETL (unchanged):
                                            - financial_etl.py
                                            - sec_filing_etl.py
                                            - market_etl.py
                                          Athena Views (unchanged)
                                          Bedrock AI Analysis (unchanged)
```

### 3. Example SDK Usage

```python
from airbyte_agent_sdk import connect

async def refresh_reit_filings():
    """Replace SEC EDGAR ingestion Lambda."""
    sec = connect("sec-edgar")  # or generic HTTP connector
    try:
        result = await sec.execute("filings", "list", params={
            "tickers": ["O", "PLD", "WELL", "AMT", "EQIX", "SPG"],
            "form_types": ["10-K", "10-Q"],
            "limit": 50,
        })
        print(f"Synced {len(result.data)} SEC filings")
    finally:
        await sec.close()
```

### 4. MCP for Ad-Hoc Queries

Add the Airbyte MCP server:

```json
{
  "mcpServers": {
    "airbyte": {
      "url": "https://mcp.airbyte.ai/mcp"
    }
  }
}
```

> "Using Airbyte MCP, query my connected REIT data. Show me the latest SEC filings for O, PLD, and SPG. What's the current cap rate environment?"

---

## Getting Started

1. **Sign up** at [app.airbyte.ai](https://app.airbyte.ai).
2. **Install the SDK**:
   ```bash
   uv add airbyte-agent-sdk
   ```
3. **Add to `.env.example`**:
   ```
   AIRBYTE_CLIENT_ID=your_client_id
   AIRBYTE_CLIENT_SECRET=***   ```
4. **Create Airbyte source configurations** for SEC EDGAR, AlphaVantage, and FRED, replacing the Lambda ingestion handlers.

---

## Connector Catalog

| Category | Connectors | Scope.Sentinel Use |
|----------|-----------|-------------------|
| **Regulatory** | SEC EDGAR (custom), OpenInsider | REIT filings, insider transactions |
| **Financial** | AlphaVantage, Yahoo Finance | REIT prices, ETF quotes |
| **Macro** | FRED | Interest rates, housing indicators, CPI |
| **Property Data** | CoStar (via API), Zillow | Property valuations, rental data |
| **Data Warehouse** | Snowflake, S3, Iceberg | Storage |

Full catalog: [docs.airbyte.com/ai-agents/connectors](https://docs.airbyte.com/ai-agents/connectors)

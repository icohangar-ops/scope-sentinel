# Scope.Sentinel — REIT Analytics Intelligence Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![AWS](https://img.shields.io/badge/AWS-Native-orange.svg)](https://aws.amazon.com/)
[![Tests](https://img.shields.io/badge/tests-147%20passing-brightgreen.svg)](tests/)

## Overview

**Scope.Sentinel** is a REIT analytics intelligence platform built on AWS native services. It ingests financial data from SEC EDGAR, market prices from AlphaVantage and FRED, and uses Amazon Bedrock (Claude Haiku) to generate composite REIT signals, FFO/AFFO analysis, dividend safety assessments, and AI-powered investment recommendations across commercial real estate sectors.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  SEC EDGAR   │  │ AlphaVantage │  │  FRED Economic Data  │  │
│  │  (Filings)   │  │  (Prices)    │  │  (Macro Indicators)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS LAMBDA (INGESTION)                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  sec_ingestion_handler.py — EventBridge Scheduled Trigger   │ │
│  │  - Fetches SEC filings for tracked REITs                   │ │
│  │  - Pulls prices from AlphaVantage / FRED                    │ │
│  │  - Writes raw data to S3                                   │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LAKE (S3 + ICEBERG)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │    reits     │  │  financial   │  │    market_indicators    │ │
│  │  (core)      │  │  _metrics    │  │    (macro data)         │ │
│  ├─────────────┤  ├──────────────┤  ├────────────────────────┤ │
│  │  sec_filing  │  │  reit_signal │  │  property_analysis     │ │
│  │  s (raw)     │  │  s (output)  │  │  (sector view)         │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────┬──────────────────┬──────────────────┬─────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                  AWS GLUE ETL PIPELINE                           │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  financial    │  │  market_data   │  │  sec_filing       │   │
│  │  _etl.py      │  │  _etl.py       │  │  _etl.py          │   │
│  │  - FFO/AFFO   │  │  - Price hist  │  │  - Parse 10-K/Q   │   │
│  │  - Peer bench │  │  - Correlation │  │  - Extract metrics │   │
│  │  - Sector avg │  │  - Trends      │  │  - Normalize data  │   │
│  └───────────────┘  └────────────────┘  └──────────────────┘   │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP FUNCTIONS (ANALYSIS ORCHESTRATION)             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  1. Compute Signal Scores (SentinelService)                │ │
│  │  2. FFO & Dividend Analysis (FinancialService)             │ │
│  │  3. Generate AI Recommendations (Bedrock Converse API)      │ │
│  │  4. Write Signals to Iceberg Tables                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 AMAZON ATHENA (QUERY ENGINE)                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  reit            │  │  property        │  │  market       │  │
│  │  _fundamentals   │  │  _analysis       │  │  _correlation │  │
│  │  .sql            │  │  .sql            │  │  .sql         │  │
│  │  - FFO rankings  │  │  - Geographic    │  │  - Rate        │  │
│  │  - Dividend safe │  │    distribution  │  │    sensitivity │  │
│  │  - Leverage      │  │  - Sector mix    │  │  - Macro       │  │
│  │    ratings       │  │  - Cap rate      │  │    signals     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               INTELLIGENCE LAYER (BEDROCK AI)                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Claude 3 Haiku via Converse API                           │ │
│  │  - Composite Sentinel Signal Generation                    │ │
│  │  - Narrative Investment Analysis                           │ │
│  │  - Risk/Opportunity Assessment                             │ │
│  │  - Sector Rotation Recommendations                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Multi-Source Data Ingestion**: SEC EDGAR (filings), AlphaVantage (prices), FRED (macro)
- **Apache Iceberg Tables**: ACID-compliant table format on S3 with time-travel queries
- **REIT Signal Engine**: Composite score (Fundamental 30% + Valuation 25% + Momentum 20% + Macro 15% + Sentiment 10%)
- **FFO/AFFO Analysis**: Funds from operations, same-store NOI growth, leverage ratings
- **Dividend Safety Scoring**: AFFO payout ratio analysis with safety ratings (Very Safe to Unsafe)
- **AI-Powered Analysis**: Claude 3 Haiku generates narrative recommendations via Bedrock Converse API
- **Sector Benchmarks**: Automatic peer comparison within REIT sub-sectors
- **Athena Views**: Pre-built analytical views for fundamentals, property, and market correlation

## Prerequisites

- Python 3.10+
- AWS account with Bedrock access enabled
- AWS credentials configured (via `.env` or IAM)
- Terraform 1.5+ (for infrastructure deployment)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your AWS credentials and API keys
```

### 3. Deploy Infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 4. Run Tests

```bash
python -m pytest tests/ -v
```

## Project Structure

```
scope-sentinel/
├── bedrock_client.py           # Bedrock Converse API wrapper
├── requirements.txt            # Python dependencies
├── src/
│   ├── models/                 # Domain models (6)
│   │   ├── reit.py             #   REIT core (ticker, sector, yield)
│   │   ├── property.py         #   Property portfolio tracking
│   │   ├── financial_metric.py #   FFO, AFFO, NOI, leverage
│   │   ├── market_indicator.py #   Interest rates, spreads, macro
│   │   ├── sec_filing.py       #   SEC filing metadata
│   │   └── reit_signal.py      #   Composite signal output
│   ├── services/               # Business logic (5)
│   │   ├── pricing_service.py  #   AlphaVantage + FRED prices
│   │   ├── financial_service.py#   FFO/AFFO computation
│   │   ├── fred_service.py     #   FRED macro indicators
│   │   ├── edgar_service.py    #   SEC EDGAR filing fetcher
│   │   └── sentinel_service.py #   Composite signal engine
│   ├── aws/                    # AWS integrations
│   │   ├── glue_scripts/       #   ETL scripts (3)
│   │   └── athena_views/       #   SQL views (3)
│   └── lambda/                 #   Lambda handlers (2)
├── terraform/                  #   Infrastructure as Code
└── tests/                      #   Test suite (147 tests)
```

## Tracked REIT Sectors

| Sector             | Sub-Sectors                              | Key Metrics                |
|--------------------|------------------------------------------|----------------------------|
| Equity REITs       | Retail, Office, Industrial, Residential  | FFO/AFFO, NOI, Cap Rate   |
| Mortgage REITs     | Agency, Non-Agency, Hybrid               | Spread, Book Value, CECL   |
| Specialty REITs    | Data Center, Cell Tower, Healthcare      | AFFO Growth, Dividend Cover|
| Infrastructure     | Pipelines, Utilities, Toll Roads         | DCF/Share, Payout Ratio   |

## Sentinel Signal Formula

```
Composite Score = (
    Fundamental Score (FFO, NOI, Growth)   × 0.30 +
    Valuation Score (NAV, Cap Rate)         × 0.25 +
    Momentum Score (Price, Volume)          × 0.20 +
    Macro Score (Rates, Spreads, GDP)       × 0.15 +
    Sentiment Score (Insider, Institutional) × 0.10
)
```

| Score Range | Rating       | Action           |
|-------------|--------------|------------------|
| 80 - 100    | Strong Buy   | Aggressive Accum |
| 65 - 79     | Buy          | Accumulate       |
| 35 - 64     | Hold         | Maintain         |
| 20 - 34     | Sell         | Reduce           |
| 0 - 19      | Strong Sell  | Exit Position    |

## API Usage

### SentinelService — Composite Signal

```python
from src.services.sentinel_service import SentinelService

svc = SentinelService()
signal = svc.generate_signal(
    ticker="O",
    fundamental_score=72.0,
    valuation_score=65.0,
    momentum_score=58.0,
    macro_score=45.0,
    sentiment_score=70.0,
)
print(f"{signal.ticker}: {signal.sentinel_score}/100 ({signal.signal_rating})")
```

### FinancialService — FFO Analysis

```python
from src.services.financial_service import FinancialService

svc = FinancialService()
ffo = svc.compute_ffo_metrics(
    net_income=120_000_000,
    depreciation=45_000_000,
    gain_on_sale=5_000_000,
    preferred_dividends=8_000_000,
    share_count=200_000_000,
)
print(f"FFO/Share: ${ffo['ffo_per_share']:.2f}")
```

### FredService — Macro Data

```python
from src.services.fred_service import FredService

svc = FredService()
rate = svc.get_fed_funds_rate()
spread = svc.get_treasury_spread(10)  # 10-Year minus 2-Year
```

## AWS Cost Estimates (Monthly)

| Service         | Usage                          | Est. Cost   |
|-----------------|--------------------------------|-------------|
| S3 Storage      | 50 GB Iceberg tables           | ~$1.20      |
| Athena Queries  | 100 queries/month              | ~$5.00      |
| Lambda          | 10K invocations                | ~$0.50      |
| Step Functions  | 500 state transitions          | ~$0.75      |
| Glue ETL        | 3 jobs x 10 min                | ~$1.50      |
| Bedrock (Haiku) | 100K tokens/month              | ~$0.25      |
| EventBridge     | 30 scheduled rules             | ~$0.30      |
| **Total**       |                                | **~$9.50**  |

## License

MIT

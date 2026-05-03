"""
Sentinel Service — Composite REIT scoring and Bedrock AI analysis.

Combines fundamental, valuation, momentum, macro, and sentiment scores
into a weighted Sentinel Score (0-100), generates AI-powered narratives
via Bedrock Converse API, and produces investment recommendations.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.models.financial_metric import FinancialMetric
from src.models.reit import REIT, REITSector
from src.models.reit_signal import REITSignal, SCORE_WEIGHTS, SignalRating

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior REIT equity research analyst with 20+ years of experience
covering all REIT sectors. You provide data-driven analysis focused on:
- Fundamentals (FFO/AFFO growth, same-store NOI, occupancy trends)
- Valuation (P/FFO multiples, cap rates, dividend yields)
- Macro environment (interest rates, Fed policy, housing market)
- Sector dynamics (supply/demand, secular trends, disruption risks)
- Risk factors (leverage, concentration, geographic exposure)

Your analysis should be concise, actionable, and include specific data points.
Always provide both risks and opportunities. Rate your confidence in the thesis."""


class SentinelService:
    """Service for composite REIT scoring and AI analysis."""

    def __init__(self, bedrock_client: Optional[Any] = None) -> None:
        if bedrock_client is None:
            from bedrock_client import BedrockClient
            load_dotenv()
            self._client = BedrockClient()
        else:
            self._client = bedrock_client

        self._financial_svc = None
        self._pricing_svc = None
        self._fred_svc = None

    def set_services(
        self,
        financial_svc: Any,
        pricing_svc: Any = None,
        fred_svc: Any = None,
    ) -> None:
        """Inject service dependencies."""
        self._financial_svc = financial_svc
        self._pricing_svc = pricing_svc
        self._fred_svc = fred_svc

    def compute_fundamental_score(self, ticker: str) -> float:
        """Compute fundamental score (0-100) based on financial metrics."""
        if not self._financial_svc:
            return 50.0

        metric = self._financial_svc.get_latest_metric(ticker)
        if not metric:
            return 50.0

        score = 50.0

        # FFO growth (max +20)
        if metric.ffo_growth_yoy > 10:
            score += 20
        elif metric.ffo_growth_yoy > 5:
            score += 15
        elif metric.ffo_growth_yoy > 0:
            score += 10
        elif metric.ffo_growth_yoy > -5:
            score += 0
        else:
            score -= 15

        # Same-store NOI growth (max +20)
        if metric.same_store_noi_growth > 5:
            score += 20
        elif metric.same_store_noi_growth > 2:
            score += 15
        elif metric.same_store_noi_growth > 0:
            score += 8
        else:
            score -= 10

        # Leverage (max +10)
        if metric.net_debt_to_ebitda < 3.0:
            score += 10
        elif metric.net_debt_to_ebitda < 5.0:
            score += 5
        elif metric.net_debt_to_ebitda > 7.0:
            score -= 10

        # Interest coverage (max +5)
        if metric.interest_coverage > 5:
            score += 5
        elif metric.interest_coverage > 3:
            score += 3

        return max(0, min(100, score))

    def compute_valuation_score(self, ticker: str) -> float:
        """Compute valuation score (0-100) — higher = more undervalued."""
        reit_data = self._financial_svc._reits.get(ticker) if self._financial_svc else None
        if not reit_data:
            return 50.0

        score = 50.0

        # Dividend yield assessment (higher yield = better value, but not too high)
        yield_score = min(reit_data.dividend_yield / 8.0, 1.0) * 30
        score += yield_score

        # Payout ratio (moderate is ideal)
        if 0.50 <= reit_data.payout_ratio <= 0.75:
            score += 15
        elif 0.40 <= reit_data.payout_ratio <= 0.85:
            score += 8
        elif reit_data.payout_ratio > 0.90:
            score -= 15

        # FFO yield (from FFO per share and dividend)
        if reit_data.latest_ffo_per_share > 0:
            ffo_yield = reit_data.dividend_yield / reit_data.payout_ratio if reit_data.payout_ratio > 0 else 0
            if ffo_yield > 0.08:
                score += 10
            elif ffo_yield > 0.06:
                score += 5

        return max(0, min(100, score))

    def compute_momentum_score(self, ticker: str) -> float:
        """Compute momentum score (0-100) from price data."""
        if not self._pricing_svc:
            return 50.0

        summary = self._pricing_svc.get_reit_summary(ticker)
        if "error" in summary:
            return 50.0

        score = 50.0
        returns = summary.get("returns_pct", {})

        # 3-month return
        ret_3m = returns.get("return_3m", 0)
        if ret_3m > 10:
            score += 25
        elif ret_3m > 5:
            score += 15
        elif ret_3m > 0:
            score += 8
        elif ret_3m > -10:
            score -= 5
        else:
            score -= 20

        # 1-year return
        ret_1y = returns.get("return_1y", 0)
        if ret_1y > 20:
            score += 15
        elif ret_1y > 10:
            score += 10
        elif ret_1y > 0:
            score += 5
        elif ret_1y < -15:
            score -= 15

        # Moving average positioning
        mas = summary.get("moving_averages", {})
        pct_200 = mas.get("pct_from_ma_200")
        if pct_200 is not None:
            if pct_200 > 10:
                score += 10
            elif pct_200 > 0:
                score += 5
            elif pct_200 < -10:
                score -= 10

        return max(0, min(100, score))

    def compute_macro_score(self) -> float:
        """Compute macro score (0-100) based on interest rate environment."""
        if not self._fred_svc:
            return 50.0

        try:
            env = self._fred_svc.analyze_rate_environment()
        except Exception:
            return 50.0

        score = 50.0

        # Rate assessment
        assessment = env.get("rate_assessment", "Neutral")
        if assessment == "Accommodative":
            score += 20
        elif assessment == "Restrictive":
            score -= 20

        # Yield curve
        curve = env.get("curve_assessment", "Normal")
        if curve == "Normal" or curve == "Steep":
            score += 10
        elif curve == "Inverted":
            score -= 15

        # Rate trend
        trend = env.get("rate_trend", "Stable")
        if trend == "Falling":
            score += 15
        elif trend == "Rising":
            score -= 10

        # Unemployment (moderate is good for REITs)
        unemployment = env.get("unemployment_rate")
        if unemployment is not None:
            if 3.5 <= unemployment <= 5.0:
                score += 5
            elif unemployment > 6.0:
                score -= 10

        return max(0, min(100, score))

    def compute_sentiment_score(self, ticker: str) -> float:
        """Compute sentiment score (0-100) based on various indicators."""
        score = 50.0

        if not self._financial_svc:
            return score

        metric = self._financial_svc.get_latest_metric(ticker)
        reit = self._financial_svc._reits.get(ticker)

        if metric:
            # Dividend growth as positive sentiment
            if metric.dividend_growth_yoy > 5:
                score += 15
            elif metric.dividend_growth_yoy > 0:
                score += 8
            elif metric.dividend_growth_yoy < 0:
                score -= 10

            # NOI growth momentum
            if metric.same_store_noi_growth > 3:
                score += 10
            elif metric.same_store_noi_growth < 0:
                score -= 10

        if reit:
            # Market cap premium (large = more stable sentiment)
            if reit.market_cap > 50_000_000_000:
                score += 10
            elif reit.market_cap > 20_000_000_000:
                score += 5

        return max(0, min(100, score))

    def generate_signal(self, ticker: str) -> REITSignal:
        """Generate a full composite signal for a REIT."""
        fundamental = self.compute_fundamental_score(ticker)
        valuation = self.compute_valuation_score(ticker)
        momentum = self.compute_momentum_score(ticker)
        macro = self.compute_macro_score()
        sentiment = self.compute_sentiment_score(ticker)

        signal = REITSignal.create(
            reit_ticker=ticker,
            fundamental=fundamental,
            valuation=valuation,
            momentum=momentum,
            macro=macro,
            sentiment=sentiment,
        )

        return signal

    def generate_ai_analysis(self, signal: REITSignal, context: Dict = None) -> str:
        """Generate AI narrative analysis using Bedrock Converse API."""
        reit = self._financial_svc._reits.get(signal.reit_ticker) if self._financial_svc else None
        metric = self._financial_svc.get_latest_metric(signal.reit_ticker) if self._financial_svc else None

        prompt = f"""Analyze {signal.reit_ticker} ({reit.name if reit else 'Unknown'}) REIT:

Sentinel Score: {signal.sentinel_score:.1f}/100 ({signal.signal_rating.value})
- Fundamental: {signal.fundamental_score:.0f}/100
- Valuation: {signal.valuation_score:.0f}/100
- Momentum: {signal.momentum_score:.0f}/100
- Macro: {signal.macro_score:.0f}/100
- Sentiment: {signal.sentiment_score:.0f}/100
"""

        if reit:
            prompt += f"""
Sector: {reit.sector.value} ({reit.sub_sector})
Market Cap: ${reit.market_cap / 1e9:.1f}B
Dividend Yield: {reit.dividend_yield:.1f}%
FFO/Share: ${reit.latest_ffo_per_share:.2f}
Payout Ratio: {reit.payout_ratio:.0%}
"""

        if metric:
            prompt += f"""
Latest Quarter: FY{metric.fiscal_year} Q{metric.quarter}
Same-Store NOI Growth: {metric.same_store_noi_growth:.1f}%
FFO Growth YoY: {metric.ffo_growth_yoy:.1f}%
Debt/EBITDA: {metric.net_debt_to_ebitda:.1f}x
Dividend Safety: {metric.dividend_safety}
"""

        if context:
            prompt += f"\nAdditional Context:\n{json.dumps(context, indent=2)}\n"

        prompt += """
Provide a 2-3 paragraph investment analysis covering:
1. Key strengths and the investment thesis
2. Primary risks and concerns
3. Actionable recommendation (Buy/Hold/Sell with rationale)
Rate your confidence in this analysis (0-100%).
"""

        try:
            analysis = self._client.chat(prompt, system=SYSTEM_PROMPT, max_tokens=800)
            return analysis
        except Exception as e:
            logger.error(f"Bedrock analysis failed for {signal.reit_ticker}: {e}")
            return f"AI analysis unavailable. Error: {str(e)}"

    def generate_full_report(self, ticker: str, context: Dict = None) -> REITSignal:
        """Generate signal with full AI analysis and risk/opportunity identification."""
        signal = self.generate_signal(ticker)

        # AI analysis
        signal.ai_analysis = self.generate_ai_analysis(signal, context)

        # Identify risks based on scores
        if signal.fundamental_score < 40:
            signal.key_risks.append("Weak fundamental performance (low FFO/NOI growth)")
        if signal.valuation_score < 35:
            signal.key_risks.append("Potentially overvalued relative to fundamentals")
        if signal.macro_score < 40:
            signal.key_risks.append("Unfavorable macro environment (rising rates, inverted curve)")
        if self._financial_svc:
            metric = self._financial_svc.get_latest_metric(ticker)
            if metric and metric.net_debt_to_ebitda > 6.0:
                signal.key_risks.append(f"High leverage at {metric.net_debt_to_ebitda:.1f}x Debt/EBITDA")

        # Identify opportunities
        if signal.fundamental_score > 70:
            signal.key_opportunities.append("Strong fundamental momentum (FFO/NOI growth)")
        if signal.valuation_score > 70:
            signal.key_opportunities.append("Attractive valuation with high dividend yield")
        if signal.macro_score > 70:
            signal.key_opportunities.append("Favorable macro tailwinds (falling rates, steep curve)")

        # Confidence score based on data completeness
        has_fundamentals = bool(self._financial_svc and self._financial_svc.get_latest_metric(ticker))
        has_prices = bool(self._pricing_svc)
        has_macro = bool(self._fred_svc)
        confidence = sum([has_fundamentals, has_prices, has_macro]) / 3.0
        signal.confidence_score = round(confidence, 2)

        signal.data_sources = []
        if has_fundamentals:
            signal.data_sources.append("financial_metrics")
        if has_prices:
            signal.data_sources.append("alpha_vantage")
        if has_macro:
            signal.data_sources.append("fred")

        return signal

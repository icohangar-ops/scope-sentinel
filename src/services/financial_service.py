"""
Financial Service — REIT financial analysis and peer comparison.

Computes FFO/AFFO comparisons, same-store NOI growth rankings,
dividend safety, leverage analysis, valuation multiples, and
sector-relative scoring.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.models.financial_metric import FinancialMetric
from src.models.reit import REIT, REITSector

logger = logging.getLogger(__name__)


class FinancialService:
    """Service for REIT financial analysis and peer comparison."""

    def __init__(self) -> None:
        self._financials: Dict[str, List[FinancialMetric]] = {}
        self._reits: Dict[str, REIT] = {}

    def load_financials(self, metrics: List[FinancialMetric]) -> None:
        """Load financial metrics into the service."""
        for m in metrics:
            self._financials.setdefault(m.reit_ticker, []).append(m)
        # Sort by fiscal year and quarter descending
        for ticker in self._financials:
            self._financials[ticker].sort(
                key=lambda m: (m.fiscal_year, m.quarter), reverse=True
            )

    def load_reits(self, reits: List[REIT]) -> None:
        """Load REIT master data."""
        for reit in reits:
            self._reits[reit.ticker] = reit

    def get_latest_metric(self, ticker: str) -> Optional[FinancialMetric]:
        """Get the most recent financial metric for a ticker."""
        metrics = self._financials.get(ticker, [])
        return metrics[0] if metrics else None

    def get_sector_peers(self, ticker: str) -> List[str]:
        """Get tickers of REITs in the same sector."""
        reit = self._reits.get(ticker)
        if not reit:
            return []
        return [
            r.ticker for r in self._reits.values()
            if r.sector == reit.sector and r.ticker != ticker
        ]

    def compute_peer_comparison(self, ticker: str) -> Dict[str, Any]:
        """Compute peer comparison metrics for a REIT within its sector."""
        metric = self.get_latest_metric(ticker)
        if not metric:
            return {"ticker": ticker, "error": "No financial data available"}

        peers = self.get_sector_peers(ticker)
        peer_metrics = []
        for peer in peers:
            pm = self.get_latest_metric(peer)
            if pm:
                peer_metrics.append(pm)

        if not peer_metrics:
            return {
                "ticker": ticker,
                "sector": self._reits.get(ticker, REIT(ticker=ticker, name=ticker, sector=REITSector.SPECIALTY)).sector.value,
                "ffo_rank": 1,
                "noi_growth_rank": 1,
                "dividend_yield_rank": 1,
                "peer_count": 0,
            }

        # FFO per share ranking
        all_ffo = sorted(
            [metric] + peer_metrics,
            key=lambda m: m.ffo_per_share,
            reverse=True,
        )
        ffo_rank = next(i for i, m in enumerate(all_ffo) if m.reit_ticker == ticker) + 1

        # Same-store NOI growth ranking
        all_noi = sorted(
            [metric] + peer_metrics,
            key=lambda m: m.same_store_noi_growth,
            reverse=True,
        )
        noi_rank = next(i for i, m in enumerate(all_noi) if m.reit_ticker == ticker) + 1

        # Dividend yield ranking (from REIT master data)
        all_yields = sorted(
            [self._reits.get(t, REIT(ticker=t, name=t, sector=REITSector.SPECIALTY)) for t in [ticker] + peers],
            key=lambda r: r.dividend_yield,
            reverse=True,
        )
        yield_rank = next(i for i, r in enumerate(all_yields) if r.ticker == ticker) + 1

        # Average peer values
        avg_ffo = sum(m.ffo_per_share for m in peer_metrics) / len(peer_metrics)
        avg_noi_growth = sum(m.same_store_noi_growth for m in peer_metrics) / len(peer_metrics)
        avg_leverage = sum(m.net_debt_to_ebitda for m in peer_metrics) / len(peer_metrics)

        return {
            "ticker": ticker,
            "sector": self._reits.get(ticker, REIT(ticker=ticker, name=ticker, sector=REITSector.SPECIALTY)).sector.value,
            "peer_count": len(peer_metrics),
            "ffo_per_share": metric.ffo_per_share,
            "ffo_rank": ffo_rank,
            "ffo_vs_peers": round(metric.ffo_per_share - avg_ffo, 2),
            "noi_growth": metric.same_store_noi_growth,
            "noi_growth_rank": noi_rank,
            "noi_growth_vs_peers": round(metric.same_store_noi_growth - avg_noi_growth, 2),
            "dividend_yield_rank": yield_rank,
            "leverage": metric.net_debt_to_ebitda,
            "leverage_vs_peers": round(metric.net_debt_to_ebitda - avg_leverage, 2),
            "avg_peer_ffo": round(avg_ffo, 2),
            "avg_peer_noi_growth": round(avg_noi_growth, 2),
            "avg_peer_leverage": round(avg_leverage, 2),
        }

    def analyze_dividend_safety(self, ticker: str) -> Dict[str, Any]:
        """Analyze dividend safety for a REIT."""
        metric = self.get_latest_metric(ticker)
        reit = self._reits.get(ticker)
        if not metric or not reit:
            return {"ticker": ticker, "error": "Insufficient data"}

        affo_payout = metric.affo_payout_ratio
        ffo_payout = metric.ffo_payout_ratio

        # Coverage assessment
        coverage = 1.0 - affo_payout if affo_payout <= 1.0 else 0.0

        # Growth vs dividend growth spread
        spread = metric.affo_yield_spread

        # Safety score (0-100)
        safety_score = 50.0
        if affo_payout <= 0.60:
            safety_score += 30
        elif affo_payout <= 0.70:
            safety_score += 20
        elif affo_payout <= 0.80:
            safety_score += 10
        elif affo_payout > 0.90:
            safety_score -= 20
        elif affo_payout > 1.0:
            safety_score -= 40

        if spread > 2.0:
            safety_score += 15
        elif spread > 0:
            safety_score += 5
        elif spread < -2.0:
            safety_score -= 15

        if metric.ffo_growth_yoy > 5.0:
            safety_score += 5
        elif metric.ffo_growth_yoy < 0:
            safety_score -= 10

        safety_score = max(0, min(100, safety_score))

        return {
            "ticker": ticker,
            "affo_payout_ratio": round(affo_payout, 4),
            "ffo_payout_ratio": round(ffo_payout, 4),
            "dividend_safety": metric.dividend_safety,
            "affo_coverage": round(coverage, 4),
            "ffo_growth_vs_div_growth": round(spread, 2),
            "safety_score": safety_score,
            "risk_level": "Low" if safety_score >= 70 else "Moderate" if safety_score >= 40 else "High",
        }

    def compute_valuation(self, ticker: str) -> Dict[str, Any]:
        """Compute valuation metrics for a REIT."""
        metric = self.get_latest_metric(ticker)
        reit = self._reits.get(ticker)
        if not metric or not reit:
            return {"ticker": ticker, "error": "Insufficient data"}

        # P/FFO
        p_ffo = (reit.market_cap / reit.latest_ffo_per_share) / (reit.market_cap / reit.market_cap) if reit.latest_ffo_per_share > 0 else 0
        # Simplified: use FFO yield
        ffo_yield = reit.dividend_yield / reit.payout_ratio if reit.payout_ratio > 0 else 0
        p_ffo = 1.0 / ffo_yield if ffo_yield > 0 else 0

        # EV/EBITDA approximation
        estimated_ebitda = metric.same_store_noi * 1.15  # NOI to EBITDA proxy
        ev_ebitda = reit.market_cap / (estimated_ebitda * 1_000_000) if estimated_ebitda > 0 else 0

        # Dividend yield vs sector
        peers = self.get_sector_peers(ticker)
        peer_yields = [self._reits.get(p, REIT(ticker=p, name=p, sector=REITSector.SPECIALTY)).dividend_yield for p in peers]
        avg_yield = sum(peer_yields) / len(peer_yields) if peer_yields else reit.dividend_yield

        return {
            "ticker": ticker,
            "p_ffo": round(p_ffo, 2),
            "ffo_yield": round(affo_yield * 100, 2) if (affo_yield := (reit.dividend_yield / reit.payout_ratio if reit.payout_ratio > 0 else 0)) else 0,
            "dividend_yield": reit.dividend_yield,
            "dividend_yield_vs_sector": round(reit.dividend_yield - avg_yield, 2),
            "avg_sector_yield": round(avg_yield, 2),
            "ev_ebitda": round(ev_ebitda, 1),
            "cap_rate": metric.weighted_avg_cap_rate,
        }

    def compute_sector_benchmarks(self) -> Dict[str, Dict[str, float]]:
        """Compute aggregate benchmarks for each sector."""
        sector_data: Dict[str, List[Dict]] = {}

        for ticker, metrics in self._financials.items():
            if not metrics:
                continue
            latest = metrics[0]
            reit = self._reits.get(ticker)
            if not reit:
                continue
            sector = reit.sector.value
            sector_data.setdefault(sector, []).append({
                "ffo": latest.ffo_per_share,
                "noi_growth": latest.same_store_noi_growth,
                "leverage": latest.net_debt_to_ebitda,
                "yield": reit.dividend_yield,
                "cap_rate": latest.weighted_avg_cap_rate,
            })

        benchmarks: Dict[str, Dict[str, float]] = {}
        for sector, data_points in sector_data.items():
            n = len(data_points)
            benchmarks[sector] = {
                "reit_count": n,
                "avg_ffo": round(sum(d["ffo"] for d in data_points) / n, 2),
                "avg_noi_growth": round(sum(d["noi_growth"] for d in data_points) / n, 2),
                "avg_leverage": round(sum(d["leverage"] for d in data_points) / n, 2),
                "avg_yield": round(sum(d["yield"] for d in data_points) / n, 2),
                "avg_cap_rate": round(sum(d["cap_rate"] for d in data_points) / n, 4),
            }

        return benchmarks

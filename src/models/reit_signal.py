"""
REITSignal domain model — composite analysis output for a REIT.

Combines fundamental, valuation, momentum, macro, and sentiment scores
into a single Sentinel Score (0-100) with AI-generated narrative analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class SignalRating(str, Enum):
    """Signal rating bands based on composite score."""
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"
    STRONG_SELL = "Strong Sell"


class Sentiment(str, Enum):
    """Market sentiment classification."""
    VERY_BULLISH = "Very Bullish"
    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"
    VERY_BEARISH = "Very Bearish"


# Weight allocations for composite score
SCORE_WEIGHTS = {
    "fundamental": 0.30,
    "valuation": 0.25,
    "momentum": 0.20,
    "macro": 0.15,
    "sentiment": 0.10,
}


@dataclass
class REITSignal:
    """Composite analysis output for a REIT."""

    signal_id: str = ""
    reit_ticker: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # Component scores (0-100)
    fundamental_score: float = 50.0
    valuation_score: float = 50.0
    momentum_score: float = 50.0
    macro_score: float = 50.0
    sentiment_score: float = 50.0

    # Composite
    sentinel_score: float = 50.0
    signal_rating: SignalRating = SignalRating.HOLD
    sentiment: Sentiment = Sentiment.NEUTRAL

    # AI analysis
    ai_analysis: str = ""
    key_risks: List[str] = field(default_factory=list)
    key_opportunities: List[str] = field(default_factory=list)

    # Source tracking
    data_sources: List[str] = field(default_factory=list)
    confidence_score: float = 0.0

    # --- Validation ---

    def __post_init__(self) -> None:
        self.reit_ticker = self.reit_ticker.strip().upper()
        if not self.signal_id:
            self.signal_id = self._generate_id()
        self._compute_composite()

    # --- Serialization ---

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "signal_id": self.signal_id,
            "reit_ticker": self.reit_ticker,
            "generated_at": self.generated_at.isoformat(),
            "fundamental_score": self.fundamental_score,
            "valuation_score": self.valuation_score,
            "momentum_score": self.momentum_score,
            "macro_score": self.macro_score,
            "sentiment_score": self.sentiment_score,
            "sentinel_score": self.sentinel_score,
            "signal_rating": self.signal_rating.value if isinstance(self.signal_rating, SignalRating) else self.signal_rating,
            "sentiment": self.sentiment.value if isinstance(self.sentiment, Sentiment) else self.sentiment,
            "ai_analysis": self.ai_analysis,
            "key_risks": self.key_risks,
            "key_opportunities": self.key_opportunities,
            "data_sources": self.data_sources,
            "confidence_score": self.confidence_score,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> REITSignal:
        """Deserialize from dictionary."""
        if "signal_rating" in data and isinstance(data["signal_rating"], str):
            data["signal_rating"] = SignalRating(data["signal_rating"])
        if "sentiment" in data and isinstance(data["sentiment"], str):
            data["sentiment"] = Sentiment(data["sentiment"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # --- Private Methods ---

    def _generate_id(self) -> str:
        """Generate deterministic signal ID."""
        ts = self.generated_at.strftime("%Y%m%d_%H%M%S")
        return f"{self.reit_ticker}_{ts}" if self.reit_ticker else f"signal_{ts}"

    def _compute_composite(self) -> None:
        """Compute weighted composite score and rating."""
        self.sentinel_score = (
            self.fundamental_score * SCORE_WEIGHTS["fundamental"]
            + self.valuation_score * SCORE_WEIGHTS["valuation"]
            + self.momentum_score * SCORE_WEIGHTS["momentum"]
            + self.macro_score * SCORE_WEIGHTS["macro"]
            + self.sentiment_score * SCORE_WEIGHTS["sentiment"]
        )
        self.sentinel_score = round(self.sentinel_score, 2)
        self.signal_rating = self._score_to_rating(self.sentinel_score)
        self.sentiment = self._score_to_sentiment(self.sentinel_score)

    @staticmethod
    def _score_to_rating(score: float) -> SignalRating:
        """Convert numeric score to SignalRating."""
        if score >= 80:
            return SignalRating.STRONG_BUY
        elif score >= 65:
            return SignalRating.BUY
        elif score >= 35:
            return SignalRating.HOLD
        elif score >= 20:
            return SignalRating.SELL
        return SignalRating.STRONG_SELL

    @staticmethod
    def _score_to_sentiment(score: float) -> Sentiment:
        """Convert numeric score to Sentiment."""
        if score >= 85:
            return Sentiment.VERY_BULLISH
        elif score >= 65:
            return Sentiment.BULLISH
        elif score >= 40:
            return Sentiment.NEUTRAL
        elif score >= 20:
            return Sentiment.BEARISH
        return Sentiment.VERY_BEARISH

    # --- Class Methods ---

    @classmethod
    def create(
        cls,
        reit_ticker: str,
        fundamental: float = 50.0,
        valuation: float = 50.0,
        momentum: float = 50.0,
        macro: float = 50.0,
        sentiment: float = 50.0,
    ) -> REITSignal:
        """Factory method to create a signal with component scores."""
        return cls(
            reit_ticker=reit_ticker,
            fundamental_score=fundamental,
            valuation_score=valuation,
            momentum_score=momentum,
            macro_score=macro,
            sentiment_score=sentiment,
        )

    @classmethod
    def compare_signals(cls, signals: List[REITSignal]) -> List[Dict]:
        """Compare multiple signals and return ranked list."""
        ranked = sorted(signals, key=lambda s: s.sentinel_score, reverse=True)
        return [
            {
                "rank": i + 1,
                "ticker": s.reit_ticker,
                "sentinel_score": s.sentinel_score,
                "rating": s.signal_rating.value,
                "fundamental": s.fundamental_score,
                "valuation": s.valuation_score,
                "momentum": s.momentum_score,
                "macro": s.macro_score,
                "sentiment": s.sentiment_score,
            }
            for i, s in enumerate(ranked)
        ]

    def __repr__(self) -> str:
        return (
            f"REITSignal(ticker={self.reit_ticker!r}, score={self.sentinel_score:.1f}, "
            f"rating={self.signal_rating.value})"
        )

"""
SECFiling domain model — SEC EDGAR filing records.

Tracks 10-K, 10-Q, and 8-K filings for REITs, including extracted text,
key financial metrics parsed from filing content, and processing status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class FilingType(str, Enum):
    """SEC filing types relevant to REITs."""
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"
    TEN_K_A = "10-K/A"
    TEN_Q_A = "10-Q/A"
    DEFI4A = "DEF 14A"
    SC13D = "SC 13D"


class FilingStatus(str, Enum):
    """Processing status of a filing."""
    PENDING = "Pending"
    DOWNLOADED = "Downloaded"
    EXTRACTED = "Extracted"
    PARSED = "Parsed"
    FAILED = "Failed"


@dataclass
class SECFiling:
    """SEC EDGAR filing record for a REIT."""

    filing_id: str
    reit_ticker: str
    cik: str
    form_type: FilingType = FilingType.TEN_K
    filing_date: str = ""
    period_ending: str = ""
    document_url: str = ""
    extracted_text: str = ""
    key_metrics_extracted: Dict = field(default_factory=dict)
    status: FilingStatus = FilingStatus.PENDING
    error_message: str = ""
    file_size_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    # --- Validation ---

    def __post_init__(self) -> None:
        self.reit_ticker = self.reit_ticker.strip().upper()
        if not self.filing_id:
            raise ValueError("Filing ID must be non-empty")
        if not self.cik:
            raise ValueError("CIK must be non-empty")

    # --- Serialization ---

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "filing_id": self.filing_id,
            "reit_ticker": self.reit_ticker,
            "cik": self.cik,
            "form_type": self.form_type.value if isinstance(self.form_type, FilingType) else self.form_type,
            "filing_date": self.filing_date,
            "period_ending": self.period_ending,
            "document_url": self.document_url,
            "extracted_text": self.extracted_text[:500],
            "key_metrics_extracted": self.key_metrics_extracted,
            "status": self.status.value if isinstance(self.status, FilingStatus) else self.status,
            "error_message": self.error_message,
            "file_size_bytes": self.file_size_bytes,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> SECFiling:
        """Deserialize from dictionary."""
        if "form_type" in data and isinstance(data["form_type"], str):
            data["form_type"] = FilingType(data["form_type"])
        if "status" in data and isinstance(data["status"], str):
            data["status"] = FilingStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # --- Class Methods ---

    @classmethod
    def build_filing_id(cls, reit_ticker: str, form_type: str, filing_date: str) -> str:
        """Generate a deterministic filing ID."""
        return f"{reit_ticker}_{form_type}_{filing_date}".replace("-", "").replace(" ", "_")

    # --- Methods ---

    def mark_downloaded(self, url: str, size: int) -> None:
        """Mark filing as downloaded."""
        self.status = FilingStatus.DOWNLOADED
        self.document_url = url
        self.file_size_bytes = size

    def mark_extracted(self, text: str) -> None:
        """Mark filing as text-extracted."""
        self.status = FilingStatus.EXTRACTED
        self.extracted_text = text

    def mark_parsed(self, metrics: Dict) -> None:
        """Mark filing as fully parsed with extracted metrics."""
        self.status = FilingStatus.PARSED
        self.key_metrics_extracted = metrics
        self.processed_at = datetime.utcnow()

    def mark_failed(self, error: str) -> None:
        """Mark filing processing as failed."""
        self.status = FilingStatus.FAILED
        self.error_message = error

    def get_extracted_metric(self, key: str, default: Optional[float] = None) -> Optional[float]:
        """Safely retrieve an extracted metric value."""
        val = self.key_metrics_extracted.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def __repr__(self) -> str:
        return (
            f"SECFiling(ticker={self.reit_ticker!r}, form={self.form_type.value}, "
            f"date={self.filing_date!r}, status={self.status.value})"
        )

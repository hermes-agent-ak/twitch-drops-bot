"""Abstract base class for drop campaign sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib


@dataclass
class Campaign:
    """A detected drop campaign."""

    source: str
    game: str
    campaign_name: str
    starts_at: int  # unix timestamp (seconds)
    ends_at: int = 0  # unix timestamp (seconds), 0 if unknown

    def compute_id(self) -> str:
        """Unique identifier for deduplication."""
        raw = f"{self.source}:{self.campaign_name}:{self.starts_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class BaseSource(ABC):
    """Abstract source for drop campaign detection."""

    name: str

    @abstractmethod
    async def fetch(self) -> list[Campaign]:
        """Fetch campaigns from this source. Returns empty list if none active."""
        ...

    async def health_check(self) -> bool:
        """Return True if source is reachable and working."""
        return True

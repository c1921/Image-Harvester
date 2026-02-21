"""Fetcher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import FetchResult


class BaseFetcher(ABC):
    """Abstract page fetcher."""

    @abstractmethod
    def fetch(self, url: str, timeout_sec: float) -> FetchResult:
        """Fetch page HTML."""

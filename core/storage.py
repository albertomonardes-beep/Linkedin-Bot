"""Deduplication storage — persists seen job URLs to seen_jobs.json."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapers.base import JobListing

logger = logging.getLogger(__name__)

EXPIRY_DAYS = 30
EXPIRY_SECONDS = EXPIRY_DAYS * 86_400

DEFAULT_PATH = Path(__file__).parent.parent / "seen_jobs.json"


class Storage:
    """Thread-unsafe but process-safe (atomic writes) JSON storage."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._data: dict[str, float] = {}  # url → unix timestamp first seen
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_new(self, job: "JobListing") -> bool:
        """Return True if this job hasn't been seen before."""
        return job.unique_id() not in self._data

    def mark_seen(self, job: "JobListing") -> None:
        """Record a job as seen (now)."""
        self._data[job.unique_id()] = time.time()

    def save(self) -> None:
        """Atomically write current state to disk after pruning expired entries."""
        self._prune()
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            logger.debug("Storage saved (%d entries).", len(self._data))
        except Exception as exc:
            logger.error("Failed to save storage: %s", exc)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def new_jobs(self, jobs: list["JobListing"]) -> list["JobListing"]:
        """Filter a list to only new (not-yet-seen) jobs."""
        return [j for j in jobs if self.is_new(j)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            logger.debug("No existing storage at %s — starting fresh.", self.path)
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            # Accept both {url: timestamp} and legacy {url: {}} formats
            self._data = {
                k: float(v) if isinstance(v, (int, float)) else time.time()
                for k, v in raw.items()
            }
            logger.debug("Storage loaded: %d entries.", len(self._data))
        except Exception as exc:
            logger.warning("Could not load storage, starting fresh: %s", exc)

    def _prune(self) -> None:
        now = time.time()
        before = len(self._data)
        self._data = {
            url: ts for url, ts in self._data.items() if now - ts < EXPIRY_SECONDS
        }
        pruned = before - len(self._data)
        if pruned:
            logger.debug("Pruned %d expired entries.", pruned)

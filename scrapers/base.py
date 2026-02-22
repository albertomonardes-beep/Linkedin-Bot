"""Base scraper and shared data structures."""
from __future__ import annotations

import re
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class JobListing:
    url: str
    title: str
    company: str
    location: str
    portal: str
    description: str = ""
    salary: str = ""
    # Derived
    score: Optional[int] = None
    score_reason: str = ""

    days_old: Optional[int] = None  # None = fecha desconocida (pasa el filtro)

    def unique_id(self) -> str:
        """Stable identifier for deduplication."""
        return self.url.strip().rstrip("/")


def make_session(retries: int = 3) -> requests.Session:
    """Create a requests Session with retry logic and a realistic User-Agent."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def days_old_from_text(text: str) -> Optional[int]:
    """Convierte texto de fecha relativa en español a días.

    Ejemplos: 'hace 3 días' → 3, 'hace 1 semana' → 7, 'hace 2 meses' → 60.
    Retorna None si no se puede parsear (el aviso pasa el filtro).
    """
    if not text:
        return None
    t = text.lower().strip()
    # horas → menos de 1 día
    m = re.search(r"hace\s+(\d+)\s+hora", t)
    if m:
        return 0
    # días
    m = re.search(r"hace\s+(\d+)\s+d[ií]a", t)
    if m:
        return int(m.group(1))
    # semanas
    m = re.search(r"hace\s+(\d+)\s+semana", t)
    if m:
        return int(m.group(1)) * 7
    # meses
    m = re.search(r"hace\s+(\d+)\s+mes", t)
    if m:
        return int(m.group(1)) * 30
    # "ayer"
    if "ayer" in t:
        return 1
    # "hoy"
    if "hoy" in t:
        return 0
    return None


def random_delay(min_s: float = 2.0, max_s: float = 8.0) -> None:
    """Sleep a random amount to avoid triggering rate limits."""
    time.sleep(random.uniform(min_s, max_s))


class BaseScraper(ABC):
    """Abstract base class for all job portal scrapers."""

    portal_name: str = "unknown"

    def __init__(self, keywords: list[str], locations: list[str], max_pages: int = 3):
        self.keywords = keywords
        self.locations = locations
        self.max_pages = max_pages
        self.session = make_session()

    def search(self) -> list[JobListing]:
        """Run search for all keyword/location combos. Fails silently per combo."""
        results: list[JobListing] = []
        seen_urls: set[str] = set()

        for kw in self.keywords:
            for loc in self.locations:
                try:
                    listings = self._search_one(kw, loc)
                    for job in listings:
                        uid = job.unique_id()
                        if uid not in seen_urls:
                            seen_urls.add(uid)
                            results.append(job)
                except Exception as exc:
                    logger.warning(
                        "[%s] Error searching kw=%r loc=%r: %s",
                        self.portal_name, kw, loc, exc,
                    )
        return results

    @abstractmethod
    def _search_one(self, keyword: str, location: str) -> list[JobListing]:
        """Search a single keyword+location combo across max_pages pages."""
        ...

    def get_job_detail(self, job: JobListing) -> str:
        """Optional: fetch full job description from the detail page."""
        try:
            random_delay(1, 3)
            resp = self.session.get(job.url, timeout=15)
            resp.raise_for_status()
            return self._parse_detail(resp.text)
        except Exception as exc:
            logger.debug("[%s] Could not fetch detail for %s: %s", self.portal_name, job.url, exc)
            return job.description

    def _parse_detail(self, html: str) -> str:  # noqa: ARG002
        """Override to extract description from detail page HTML."""
        return ""

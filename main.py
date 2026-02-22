#!/usr/bin/env python3
"""
Job Bot — Main orchestrator.

Searches Chilean job portals, scores listings with Claude Haiku,
deduplicates, and sends new relevant jobs to Telegram.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from scrapers import (
    TrabajandoScraper,
    LaborumScraper,
    ComputrabajoScraper,
    LinkedInScraper,
)
from scrapers.base import JobListing
from core.storage import Storage
from core.matcher import Matcher
from core.notifier import TelegramNotifier

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("job_bot")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
PREFS_PATH = ROOT / "profile" / "preferences.yaml"
CV_PATH = ROOT / "profile" / "cv.md"
SEEN_PATH = ROOT / "seen_jobs.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_preferences() -> dict:
    with open(PREFS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_cv() -> str:
    if CV_PATH.exists():
        return CV_PATH.read_text(encoding="utf-8")
    logger.warning("cv.md not found at %s — AI scoring will be less accurate.", CV_PATH)
    return ""


def run_scraper_safe(scraper_cls, keywords, locations, max_pages) -> tuple[list[JobListing], str]:
    """Run a scraper class and return (jobs, status_string)."""
    name = scraper_cls.portal_name if hasattr(scraper_cls, "portal_name") else scraper_cls.__name__
    try:
        scraper = scraper_cls(
            keywords=keywords,
            locations=locations,
            max_pages=max_pages,
        )
        jobs = scraper.search()
        logger.info("[%s] Found %d listings.", name, len(jobs))
        return jobs, "ok"
    except Exception as exc:
        logger.error("[%s] Scraper failed: %s", name, exc)
        return [], f"error: {exc}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    prefs = load_preferences()
    cv = load_cv()

    keywords: list[str] = prefs.get("job_titles", []) + prefs.get("keywords", [])
    # Deduplicate while preserving order
    seen_kw: set[str] = set()
    unique_keywords: list[str] = []
    for kw in keywords:
        if kw.lower() not in seen_kw:
            seen_kw.add(kw.lower())
            unique_keywords.append(kw)

    locations: list[str] = prefs.get("locations", ["Santiago"])
    max_pages: int = prefs.get("max_pages_per_portal", 3)
    max_jobs: int = prefs.get("max_jobs_per_run", 50)

    logger.info(
        "Starting job bot — keywords=%s, locations=%s, max_pages=%d",
        unique_keywords, locations, max_pages,
    )

    # ------------------------------------------------------------------
    # 1. Scrape all portals
    # ------------------------------------------------------------------
    all_jobs: list[JobListing] = []
    portal_statuses: dict[str, str] = {}

    scrapers = [
        TrabajandoScraper,
        LaborumScraper,
        ComputrabajoScraper,
        LinkedInScraper,
    ]

    for scraper_cls in scrapers:
        portal_name = getattr(scraper_cls, "portal_name", scraper_cls.__name__)
        jobs, status = run_scraper_safe(scraper_cls, unique_keywords, locations, max_pages)
        portal_statuses[portal_name] = status
        all_jobs.extend(jobs)

    logger.info("Total raw listings scraped: %d", len(all_jobs))

    # ------------------------------------------------------------------
    # 1b. Filtrar avisos con más de 14 días de antigüedad
    # ------------------------------------------------------------------
    max_days: int = prefs.get("max_days_old", 14)
    before_filter = len(all_jobs)
    all_jobs = [j for j in all_jobs if j.days_old is None or j.days_old <= max_days]
    logger.info(
        "After date filter (<= %d days): %d jobs (removed %d old listings)",
        max_days, len(all_jobs), before_filter - len(all_jobs),
    )

    # ------------------------------------------------------------------
    # 2. Deduplicate against seen_jobs.json
    # ------------------------------------------------------------------
    storage = Storage(SEEN_PATH)
    new_jobs = storage.new_jobs(all_jobs)
    logger.info("New (unseen) jobs: %d", len(new_jobs))

    # ------------------------------------------------------------------
    # 3. AI scoring
    # ------------------------------------------------------------------
    if not new_jobs:
        logger.info("No new jobs to process.")
        _finalize(storage, 0, 0, portal_statuses)
        return

    # Cap to avoid runaway API costs on first run
    if len(new_jobs) > max_jobs:
        logger.info("Capping to %d jobs (max_jobs_per_run).", max_jobs)
        new_jobs = new_jobs[:max_jobs]

    matcher = Matcher(cv=cv, preferences=prefs)
    relevant_jobs = matcher.filter_and_score(new_jobs)
    logger.info("Relevant jobs (above threshold): %d", len(relevant_jobs))

    # ------------------------------------------------------------------
    # 4. Send to Telegram
    # ------------------------------------------------------------------
    notifier = TelegramNotifier()
    sent = 0
    for job in relevant_jobs:
        if notifier.send_job(job):
            storage.mark_seen(job)
            sent += 1

    # Also mark non-relevant new jobs as seen (so we don't re-evaluate them)
    relevant_urls = {j.unique_id() for j in relevant_jobs}
    for job in new_jobs:
        if job.unique_id() not in relevant_urls:
            storage.mark_seen(job)

    _finalize(storage, len(new_jobs), sent, portal_statuses)


def _finalize(
    storage: Storage,
    total_found: int,
    total_sent: int,
    portal_statuses: dict[str, str],
) -> None:
    storage.save()
    logger.info("Run complete — found=%d, sent=%d", total_found, total_sent)

    try:
        notifier = TelegramNotifier()
        notifier.send_summary(total_found, total_sent, portal_statuses)
    except Exception as exc:
        logger.warning("Could not send summary: %s", exc)


if __name__ == "__main__":
    main()

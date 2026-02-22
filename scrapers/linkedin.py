"""Scraper for LinkedIn Jobs (anonymous / guest access via Playwright)."""
from __future__ import annotations

import logging
import time
import random
from urllib.parse import quote_plus

from .base import BaseScraper, JobListing

logger = logging.getLogger(__name__)

# geoId for Chile
CHILE_GEO_ID = "104621616"
BASE_URL = "https://www.linkedin.com"
SEARCH_URL = (
    BASE_URL
    + "/jobs/search?keywords={kw}&location={loc}"
    + "&geoId=" + CHILE_GEO_ID
    + "&f_TPR=r1209600"  # posted in last 14 days
)


class LinkedInScraper(BaseScraper):
    """Uses Playwright (headless Chromium) for LinkedIn guest access."""

    portal_name = "linkedin.com"

    def _search_one(self, keyword: str, location: str) -> list[JobListing]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("[linkedin] playwright not installed — skipping")
            return []

        listings: list[JobListing] = []
        url = SEARCH_URL.format(
            kw=quote_plus(keyword),
            loc=quote_plus(location),
        )
        logger.info("[linkedin] searching — %s", url)

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    locale="es-CL",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(random.uniform(2, 4))

                # Scroll to load more cards (lazy loading)
                for _ in range(min(self.max_pages, 3)):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(random.uniform(2, 4))

                    # Click "Show more results" if present
                    btn = page.query_selector("button[aria-label*='more results']")
                    if btn:
                        btn.click()
                        time.sleep(random.uniform(2, 3))

                cards = page.query_selector_all(
                    "div.base-card, li.jobs-search-results__list-item, "
                    "div[class*='job-search-card']"
                )

                for card in cards:
                    job = self._parse_card_pw(card)
                    if job:
                        listings.append(job)

                browser.close()

        except Exception as exc:
            logger.warning("[linkedin] Playwright error: %s", exc)

        return listings

    def _parse_card_pw(self, card) -> JobListing | None:  # type: ignore[type-arg]
        try:
            title_el = card.query_selector(
                "h3.base-search-card__title, h3[class*='title'], a[class*='job-title']"
            )
            if not title_el:
                return None
            title = title_el.inner_text().strip()

            link_el = card.query_selector("a.base-card__full-link, a[class*='job-card-link']")
            url = link_el.get_attribute("href") if link_el else ""
            if not url:
                return None
            # Strip tracking params
            url = url.split("?")[0]

            company_el = card.query_selector(
                "h4.base-search-card__subtitle, a[class*='company'], span[class*='company']"
            )
            company = company_el.inner_text().strip() if company_el else "N/A"

            loc_el = card.query_selector(
                "span.job-search-card__location, span[class*='location']"
            )
            location = loc_el.inner_text().strip() if loc_el else "N/A"

            salary_el = card.query_selector("span[class*='salary']")
            salary = salary_el.inner_text().strip() if salary_el else ""

            return JobListing(
                url=url,
                title=title,
                company=company,
                location=location,
                portal=self.portal_name,
                description="",  # fetched separately if needed
                salary=salary,
            )
        except Exception as exc:
            logger.debug("[linkedin] Card parse error: %s", exc)
            return None

    def _parse_detail(self, html: str) -> str:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        desc_el = soup.select_one(
            "div.show-more-less-html__markup, div[class*='description__text'], "
            "section[class*='description']"
        )
        return desc_el.get_text(separator="\n", strip=True) if desc_el else ""

"""Scraper for laborum.cl."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import BaseScraper, JobListing, random_delay, days_old_from_text

logger = logging.getLogger(__name__)

BASE_URL = "https://www.laborum.cl"
SEARCH_URL = BASE_URL + "/empleos?q={kw}&l={loc}&pg={n}"


class LaborumScraper(BaseScraper):
    portal_name = "laborum.cl"

    def _search_one(self, keyword: str, location: str) -> list[JobListing]:
        listings: list[JobListing] = []

        for page in range(1, self.max_pages + 1):
            url = SEARCH_URL.format(
                kw=quote_plus(keyword),
                loc=quote_plus(location),
                n=page,
            )
            logger.info("[laborum.cl] page %d — %s", page, url)

            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("[laborum.cl] Request failed: %s", exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(
                "article.aviso, div.aviso-item, div[class*='job-item'], li[class*='job']"
            )

            if not cards:
                logger.debug("[laborum.cl] No cards found on page %d, stopping.", page)
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    listings.append(job)

            if page < self.max_pages:
                random_delay()

        return listings

    def _parse_card(self, card: BeautifulSoup) -> JobListing | None:
        try:
            title_el = card.select_one(
                "a[class*='title'], h2 a, h3 a, a.aviso-title, span[class*='title'] a"
            )
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = href if href.startswith("http") else BASE_URL + href

            company_el = card.select_one(
                "span[class*='company'], span[class*='empresa'], a[class*='empresa']"
            )
            company = company_el.get_text(strip=True) if company_el else "N/A"

            loc_el = card.select_one(
                "span[class*='location'], span[class*='ubicacion'], li[class*='location']"
            )
            location = loc_el.get_text(strip=True) if loc_el else "N/A"

            desc_el = card.select_one("p[class*='desc'], div[class*='desc'], p[class*='summary']")
            description = desc_el.get_text(strip=True) if desc_el else ""

            salary_el = card.select_one("span[class*='salary'], span[class*='salario']")
            salary = salary_el.get_text(strip=True) if salary_el else ""

            # Date
            date_el = card.select_one(
                "span[class*='date'], span[class*='fecha'], time, span[class*='time'], "
                "div[class*='date'], p[class*='date']"
            )
            date_text = date_el.get_text(strip=True) if date_el else ""
            days = days_old_from_text(date_text)

            return JobListing(
                url=url,
                title=title,
                company=company,
                location=location,
                portal=self.portal_name,
                description=description,
                salary=salary,
                days_old=days,
            )
        except Exception as exc:
            logger.debug("[laborum.cl] Card parse error: %s", exc)
            return None

    def _parse_detail(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        desc_el = soup.select_one(
            "div[class*='job-description'], div[class*='descripcion'], section[class*='content']"
        )
        return desc_el.get_text(separator="\n", strip=True) if desc_el else ""

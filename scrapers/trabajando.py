"""Scraper for trabajando.cl."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import BaseScraper, JobListing, random_delay

logger = logging.getLogger(__name__)

BASE_URL = "https://www.trabajando.cl"
SEARCH_URL = BASE_URL + "/trabajo/resultados?q={kw}&location={loc}&page={n}"


class TrabajandoScraper(BaseScraper):
    portal_name = "trabajando.cl"

    def _search_one(self, keyword: str, location: str) -> list[JobListing]:
        listings: list[JobListing] = []

        for page in range(1, self.max_pages + 1):
            url = SEARCH_URL.format(
                kw=quote_plus(keyword),
                loc=quote_plus(location),
                n=page,
            )
            logger.info("[trabajando.cl] page %d — %s", page, url)

            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("[trabajando.cl] Request failed: %s", exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            # Main job cards container
            cards = soup.select("div.aviso-item, article.aviso, div[class*='job-card']")
            if not cards:
                # Try generic fallback selector
                cards = soup.select("div.listado-aviso")

            if not cards:
                logger.debug("[trabajando.cl] No cards found on page %d, stopping.", page)
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
            # Title + URL
            title_el = card.select_one("a.titulo-aviso, h2 a, h3 a, a[class*='title']")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = href if href.startswith("http") else BASE_URL + href

            # Company
            company_el = card.select_one(
                "span.empresa, span[class*='company'], div[class*='empresa']"
            )
            company = company_el.get_text(strip=True) if company_el else "N/A"

            # Location
            loc_el = card.select_one(
                "span.ubicacion, span[class*='location'], span[class*='ubicacion']"
            )
            location = loc_el.get_text(strip=True) if loc_el else "N/A"

            # Short description
            desc_el = card.select_one("p.descripcion, div[class*='description'], p[class*='desc']")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Salary
            salary_el = card.select_one("span[class*='salario'], span[class*='salary']")
            salary = salary_el.get_text(strip=True) if salary_el else ""

            return JobListing(
                url=url,
                title=title,
                company=company,
                location=location,
                portal=self.portal_name,
                description=description,
                salary=salary,
            )
        except Exception as exc:
            logger.debug("[trabajando.cl] Card parse error: %s", exc)
            return None

    def _parse_detail(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        desc_el = soup.select_one(
            "div.descripcion-aviso, div[class*='job-description'], section[class*='description']"
        )
        return desc_el.get_text(separator="\n", strip=True) if desc_el else ""

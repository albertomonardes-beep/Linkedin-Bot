"""AI-powered job relevance scoring using Claude Haiku."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from scrapers.base import JobListing

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 50  # max jobs per API call


def _build_system_prompt(cv: str, preferences: dict) -> str:
    titles = ", ".join(preferences.get("job_titles", []))
    keywords = ", ".join(preferences.get("keywords", []))
    locations = ", ".join(preferences.get("locations", []))
    return f"""Eres un evaluador experto de empleos. Dado un CV y preferencias de búsqueda, \
puntúas la relevancia de cada oferta laboral del 1 al 10.

## CV del candidato
{cv}

## Preferencias
- Títulos buscados: {titles}
- Keywords técnicas: {keywords}
- Ubicaciones aceptadas: {locations}

## Instrucciones
Para cada oferta en el JSON de entrada, responde con un JSON array con este formato exacto:
[
  {{"index": 0, "score": 8, "reason": "Coincide con Python y Django, ubicación remota"}},
  ...
]

Considera:
- Score 9-10: coincidencia muy alta (título + stack + ubicación)
- Score 7-8: buena coincidencia (título o stack principal)
- Score 5-6: coincidencia parcial
- Score 1-4: poco relevante
Responde SOLO con el JSON array, sin texto adicional."""


def _build_user_message(jobs: list["JobListing"]) -> str:
    items = []
    for i, job in enumerate(jobs):
        items.append({
            "index": i,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": (job.description or "")[:500],  # truncate to save tokens
            "salary": job.salary,
        })
    return json.dumps(items, ensure_ascii=False, indent=2)


def _parse_response(text: str, n_jobs: int) -> list[dict]:
    """Extract JSON array from model response, tolerating markdown fences."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: try to extract first [...] block
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse model response; assigning score 0 to all jobs.")
    return [{"index": i, "score": 0, "reason": "parse error"} for i in range(n_jobs)]


class Matcher:
    def __init__(self, cv: str, preferences: dict):
        self.cv = cv
        self.preferences = preferences
        self.threshold: int = preferences.get("relevance_threshold", 7)
        self.exclude_kws: list[str] = [
            kw.lower() for kw in preferences.get("exclude_keywords", [])
        ]
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter_and_score(self, jobs: list["JobListing"]) -> list["JobListing"]:
        """Return only jobs with score >= threshold, with score and reason attached."""
        # Phase 1: cheap keyword pre-filter (no API cost)
        jobs = self._prefilter(jobs)
        if not jobs:
            return []

        # Phase 2: AI scoring in batches
        scored: list["JobListing"] = []
        for batch_start in range(0, len(jobs), BATCH_SIZE):
            batch = jobs[batch_start: batch_start + BATCH_SIZE]
            self._score_batch(batch)
            scored.extend(batch)

        relevant = [j for j in scored if (j.score or 0) >= self.threshold]
        relevant.sort(key=lambda j: j.score or 0, reverse=True)
        logger.info(
            "Matcher: %d jobs → %d after pre-filter → %d above threshold",
            len(jobs), len(jobs), len(relevant),
        )
        return relevant

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prefilter(self, jobs: list["JobListing"]) -> list["JobListing"]:
        if not self.exclude_kws:
            return jobs
        filtered = []
        for job in jobs:
            haystack = job.title.lower()  # solo filtra por título, no descripción
            if not any(kw in haystack for kw in self.exclude_kws):
                filtered.append(job)
        excluded = len(jobs) - len(filtered)
        if excluded:
            logger.info("Pre-filter excluded %d jobs with forbidden keywords.", excluded)
        return filtered

    def _score_batch(self, batch: list["JobListing"]) -> None:
        """Call Claude Haiku and annotate jobs in-place with score + reason."""
        system = _build_system_prompt(self.cv, self.preferences)
        user_msg = _build_user_message(batch)

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            result_text = response.content[0].text
        except Exception as exc:
            logger.error("Claude API error during scoring: %s", exc)
            for job in batch:
                job.score = 0
                job.score_reason = "API error"
            return

        scores = _parse_response(result_text, len(batch))
        # Build index → result map
        score_map = {item.get("index", -1): item for item in scores}

        for i, job in enumerate(batch):
            item = score_map.get(i, {})
            job.score = int(item.get("score", 0))
            job.score_reason = item.get("reason", "")

"""Telegram notification sender."""
from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from scrapers.base import JobListing

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MSG_LEN = 4096  # Telegram limit


class TelegramNotifier:
    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
    ):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_job(self, job: "JobListing") -> bool:
        """Send a single job listing. Returns True on success."""
        text = self._format_job(job)
        return self._send(text)

    def send_summary(
        self,
        total_found: int,
        total_sent: int,
        portal_statuses: dict[str, str],
    ) -> None:
        """Send a run summary message."""
        lines = [
            "📊 *Resumen del run*",
            f"• Trabajos encontrados: {total_found}",
            f"• Enviados (score ≥ umbral): {total_sent}",
            "",
            "*Estado de portales:*",
        ]
        for portal, status in portal_statuses.items():
            icon = "✅" if status == "ok" else "⚠️"
            lines.append(f"  {icon} {portal}: {status}")

        self._send("\n".join(lines))

    def send_message(self, text: str) -> bool:
        """Send arbitrary text (plain or Markdown)."""
        return self._send(text)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _format_job(self, job: "JobListing") -> str:
        score_str = f"{job.score}/10" if job.score is not None else "N/A"
        reason = job.score_reason or ""
        salary_line = f"💰 {job.salary}\n" if job.salary else ""

        text = (
            f"🔍 *Nuevo empleo relevante* (Score: {score_str})\n"
            f"📋 *{self._escape(job.title)}*\n"
            f"🏢 {self._escape(job.company)}\n"
            f"📍 {self._escape(job.location)}\n"
            f"{salary_line}"
            f"💡 _{self._escape(reason)}_\n"
            f"\n"
            f"🔗 {job.url}\n"
            f"Portal: {job.portal}"
        )
        # Truncate if somehow over the limit
        if len(text) > MAX_MSG_LEN:
            text = text[: MAX_MSG_LEN - 3] + "..."
        return text

    @staticmethod
    def _escape(text: str) -> str:
        """Escape Markdown v1 special chars."""
        for ch in ["*", "_", "`", "["]:
            text = text.replace(ch, f"\\{ch}")
        return text

    def _send(self, text: str, parse_mode: str = "Markdown") -> bool:
        url = TELEGRAM_API.format(token=self.token, method="sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if not resp.ok:
                logger.warning("Telegram API error: %s — %s", resp.status_code, resp.text[:200])
                return False
            time.sleep(0.5)  # respect Telegram rate limit (30 msg/s)
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            return False

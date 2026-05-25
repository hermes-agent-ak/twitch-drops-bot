"""Scraper for twitch.facepunch.com — Rust's publisher-hosted drops page.

Public, no auth required. Parses setupCountdown() JavaScript calls
to extract campaign start/end timestamps.
"""

import logging
import re
import time
from datetime import datetime, timezone

import requests

from config import FACEPUNCH_URL_MAP
from sources.base import BaseSource, Campaign

logger = logging.getLogger(__name__)

# Regex to extract: setupCountdown('.campaign-0', START_MS, END_MS)
COUNTDOWN_RE = re.compile(
    r"setupCountdown\('\.([^']+)',\s*(\d+),\s*(\d+)\)"
)


class FacepunchScraper(BaseSource):
    """Scrapes twitch.facepunch.com for active drop campaigns."""

    name = "facepunch"
    TIMEOUT = 15

    async def fetch(self) -> list[Campaign]:
        """Fetch campaigns from all configured Facepunch URLs."""
        campaigns = []
        for url, game in FACEPUNCH_URL_MAP.items():
            try:
                results = await self._fetch_url(url, game)
                campaigns.extend(results)
            except Exception as e:
                logger.error("FacepunchScraper failed for %s: %s", url, e)
                raise
        return campaigns

    async def _fetch_url(self, url: str, game: str) -> list[Campaign]:
        """Scrape a single Facepunch drops URL."""
        logger.info("Fetching %s for %s", url, game)

        resp = requests.get(
            url,
            headers={"User-Agent": "TwitchDropsBot/1.0"},
            timeout=self.TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text

        campaigns = []
        for match in COUNTDOWN_RE.finditer(html):
            campaign_class = match.group(1)
            start_ms = int(match.group(2))
            end_ms = int(match.group(3))

            starts_at = start_ms // 1000
            ends_at = end_ms // 1000

            campaign = Campaign(
                source=self.name,
                game=game,
                campaign_name=f"{game} Drops ({campaign_class})",
                starts_at=starts_at,
                ends_at=ends_at,
            )

            # Only report if campaign hasn't ended yet
            now = int(time.time())
            if ends_at > now:
                campaigns.append(campaign)
                logger.info(
                    "Found active campaign: %s | %s → %s",
                    game,
                    datetime.fromtimestamp(starts_at, tz=timezone.utc),
                    datetime.fromtimestamp(ends_at, tz=timezone.utc),
                )
            else:
                logger.debug(
                    "Skipping expired campaign: %s (ended %s)",
                    game,
                    datetime.fromtimestamp(ends_at, tz=timezone.utc),
                )

        return campaigns

    async def health_check(self) -> bool:
        """Check if Facepunch pages are reachable."""
        for url in FACEPUNCH_URL_MAP:
            try:
                resp = requests.get(
                    url,
                    headers={"User-Agent": "TwitchDropsBot/1.0"},
                    timeout=self.TIMEOUT,
                )
                if resp.status_code != 200:
                    return False
            except requests.RequestException:
                return False
        return True

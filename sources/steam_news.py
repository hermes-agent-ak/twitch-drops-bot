"""Checker for Steam News API — official Valve endpoint.

Public, no auth required. Filters news titles/contents for drop-related keywords.
"""

import logging
import time
import requests

from config import DROP_KEYWORDS, STEAM_GAME_MAP
from sources.base import BaseSource, Campaign

logger = logging.getLogger(__name__)

STEAM_NEWS_API = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"


class SteamNewsChecker(BaseSource):
    """Checks Steam news for drop campaign announcements."""

    name = "steam_news"
    TIMEOUT = 15

    async def fetch(self) -> list[Campaign]:
        """Check Steam news for all configured games."""
        campaigns = []
        for appid, game in STEAM_GAME_MAP.items():
            try:
                results = await self._check_game(appid, game)
                campaigns.extend(results)
            except Exception as e:
                logger.error(
                    "SteamNewsChecker failed for %s (appid %s): %s",
                    game, appid, e,
                )
                raise
        return campaigns

    async def _check_game(self, appid: int, game: str) -> list[Campaign]:
        """Check Steam news for a specific game."""
        params = {
            "appid": appid,
            "count": 20,
            "maxlength": 500,
            "format": "json",
        }

        logger.debug("Checking Steam news for %s (appid %s)", game, appid)

        resp = requests.get(
            STEAM_NEWS_API,
            params=params,
            timeout=self.TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        news_items = data.get("appnews", {}).get("newsitems", [])
        campaigns = []

        now = int(time.time())
        cutoff = now - (7 * 86400)  # Only look at last 7 days

        for item in news_items:
            title = item.get("title", "")
            contents = item.get("contents", "")
            text = f"{title} {contents}".lower()

            # Check for drop keywords
            matched = any(kw in text for kw in DROP_KEYWORDS)
            if not matched:
                continue

            # Steam news date is unix timestamp
            news_date = item.get("date", 0)
            if news_date < cutoff:
                logger.debug(
                    "Skipping old drop news: %s (%s)", title, game
                )
                continue

            # We don't know exact start/end from Steam news alone
            # Use news date as starts_at, estimate 5-day campaign
            starts_at = news_date
            ends_at = news_date + (5 * 86400)  # assume 5-day campaign

            campaign = Campaign(
                source=self.name,
                game=game,
                campaign_name=title,
                starts_at=starts_at,
                ends_at=ends_at,
            )

            logger.info(
                "Found Steam drop news: %s | %s",
                game,
                title,
            )

            if ends_at > now:
                campaigns.append(campaign)

        return campaigns

    async def health_check(self) -> bool:
        """Check if Steam API is reachable."""
        try:
            resp = requests.get(
                STEAM_NEWS_API,
                params={"appid": 252490, "count": 1, "format": "json"},
                timeout=self.TIMEOUT,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

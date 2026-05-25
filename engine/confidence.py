"""Multi-source confidence scoring engine.

Combines results from facepunch (PRIMARY) and steam_news (CONFIRMATION)
to produce HIGH / MEDIUM / LOW confidence ratings.
"""

import logging
from collections import defaultdict

from sources.base import Campaign

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """Computes confidence scores by cross-referencing sources."""

    # Source weight/priority
    SOURCE_PRIORITY = {
        "facepunch": "primary",
        "steam_news": "secondary",
    }

    @staticmethod
    def score(campaigns: list[Campaign]) -> list[tuple[Campaign, str]]:
        """Score campaigns and return (campaign, confidence) pairs.

        Strategy:
        - Group campaigns by (game, approximate time window)
        - HIGH: facepunch + steam_news both report it
        - MEDIUM: facepunch reports it, steam_news doesn't (yet)
        - LOW: steam_news reports it, facepunch doesn't
        """
        if not campaigns:
            return []

        scored = []

        # Group by game
        by_game: dict[str, list[Campaign]] = defaultdict(list)
        for c in campaigns:
            by_game[c.game].append(c)

        for game, game_campaigns in by_game.items():
            facepunch_campaigns = [
                c for c in game_campaigns if c.source == "facepunch"
            ]
            steam_campaigns = [
                c for c in game_campaigns if c.source == "steam_news"
            ]

            # HIGH: Both sources agree
            if facepunch_campaigns and steam_campaigns:
                for fc in facepunch_campaigns:
                    # Try to find matching steam campaign within 3 days
                    matched = False
                    for sc in steam_campaigns:
                        diff = abs(fc.starts_at - sc.starts_at)
                        if diff < 3 * 86400:  # within 3 days
                            # Merge: facepunch timestamps are more accurate
                            merged = Campaign(
                                source="multi",
                                game=fc.game,
                                campaign_name=fc.campaign_name,
                                starts_at=fc.starts_at,
                                ends_at=fc.ends_at,
                            )
                            scored.append((merged, "HIGH"))
                            matched = True
                            logger.info(
                                "HIGH confidence: %s (%s + %s)",
                                game, fc.source, sc.source,
                            )
                            break
                    if not matched:
                        scored.append((fc, "MEDIUM"))

                # Remaining steam-only campaigns
                for sc in steam_campaigns:
                    already_matched = any(
                        abs(sc.starts_at - fc.starts_at) < 3 * 86400
                        for fc in facepunch_campaigns
                    )
                    if not already_matched:
                        scored.append((sc, "LOW"))

            # MEDIUM: Only facepunch
            elif facepunch_campaigns:
                for fc in facepunch_campaigns:
                    scored.append((fc, "MEDIUM"))
                    logger.info("MEDIUM confidence: %s (facepunch only)", game)

            # LOW: Only steam
            elif steam_campaigns:
                for sc in steam_campaigns:
                    scored.append((sc, "LOW"))
                    logger.info("LOW confidence: %s (steam only)", game)

        return scored

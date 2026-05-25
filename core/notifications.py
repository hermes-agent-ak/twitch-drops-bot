"""Notification service — sends messages to Telegram users.

Injectable service that handles message formatting and delivery.
No knowledge of sources, state, or scheduling.
"""

import logging
from datetime import datetime, timezone
from telegram import Bot
from state import StateManager

logger = logging.getLogger("twitch-drops-bot.notifications")

STAGE_MESSAGES = {
    "announced": (
        "📢 <b>Upcoming Twitch Drops!</b>\n\n"
        "Game: <b>{game}</b>\n"
        "Campaign: {name}\n"
        "Starts: {start}\n"
        "Ends: {end}\n"
        "Confidence: {confidence}\n\n"
        "You'll get a reminder when the drops go live."
    ),
    "reminder_24h": (
        "⏰ <b>Drops Start Tomorrow!</b>\n\n"
        "Game: <b>{game}</b>\n"
        "Campaign: {name}\n"
        "Starts: {start}\n"
        "Ends: {end}\n\n"
        "Get ready to watch and claim!"
    ),
    "live": (
        "🔴 <b>Drops Are LIVE NOW!</b>\n\n"
        "Game: <b>{game}</b>\n"
        "Campaign: {name}\n"
        "Started: {start}\n"
        "Ends: {end}\n\n"
        "Watch participating streams to claim your drops!"
    ),
    "ending_soon": (
        "⚠️ <b>Drops Ending Soon!</b>\n\n"
        "Game: <b>{game}</b>\n"
        "Campaign: {name}\n"
        "Ends: {end}\n\n"
        "Claim your drops before they're gone!"
    ),
}

CONFIDENCE_LABELS = {
    "HIGH": "HIGH ✅",
    "MEDIUM": "MEDIUM ⚠️",
    "LOW": "LOW ❔",
}


class NotificationService:
    """Sends formatted notifications to Telegram users."""

    async def send_stage_notification(
        self,
        bot: Bot,
        state: StateManager,
        campaign: dict,
        stage: str,
    ) -> int:
        """Send a stage notification for a campaign.

        Returns:
            int: Number of users notified.
        """
        if stage not in STAGE_MESSAGES:
            logger.error("Unknown notification stage: %s", stage)
            return 0

        game = campaign["game"]
        chat_ids = state.get_subscribed_users(game)

        if not chat_ids:
            logger.debug("No subscribers for %s, skipping %s", game, stage)
            return 0

        start_dt = datetime.fromtimestamp(campaign["starts_at"], tz=timezone.utc)
        end_dt = datetime.fromtimestamp(campaign["ends_at"], tz=timezone.utc)
        conf_label = CONFIDENCE_LABELS.get(
            campaign["confidence"], campaign["confidence"]
        )

        msg = STAGE_MESSAGES[stage].format(
            game=game,
            name=campaign["campaign_name"],
            start=start_dt.strftime("%Y-%m-%d %H:%M UTC"),
            end=end_dt.strftime("%Y-%m-%d %H:%M UTC"),
            confidence=conf_label,
        )

        sent = 0
        for chat_id in chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                )
                sent += 1
                logger.debug("Sent '%s' for %s to %s", stage, game, chat_id)
            except Exception as e:
                logger.error("Failed to notify %s: %s", chat_id, e)

        logger.info(
            "Sent %s notification for %s to %d/%d users",
            stage, game, sent, len(chat_ids),
        )
        return sent

    async def send_health_alert(
        self, bot: Bot, admin_chat_id: int, source_name: str,
        failures: int, error: str,
    ):
        """Send a health alert to the admin."""
        try:
            await bot.send_message(
                chat_id=admin_chat_id,
                text=(
                    f"⚠️ <b>Source Health Alert</b>\n"
                    f"Source: {source_name}\n"
                    f"Consecutive failures: {failures}\n"
                    f"Last error: {error[:200]}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Failed to send health alert: %s", e)

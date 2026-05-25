"""/testnotify command — test the notification pipeline with a fake campaign."""

import logging
import time
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("twitch-drops-bot.handlers.testnotify")


async def cmd_testnotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a test notification through the full pipeline."""
    state = context.application.bot_data["state"]
    notification_service = context.application.bot_data["notification_service"]

    await update.message.reply_text("🧪 Running notification test...")

    now = int(time.time())
    fake_campaign = {
        "id": "test_campaign_001",
        "game": "Rust",
        "campaign_name": "Test Campaign (simulated)",
        "source": "test",
        "starts_at": now - 3600,           # started 1h ago
        "ends_at": now + 86400 * 3,        # ends in 3 days
        "confidence": "HIGH",
        "notification_stage": None,
        "_next_stage": "announced",
    }

    # Also inject into DB so /status shows it
    state.upsert_campaign(
        campaign_id=fake_campaign["id"],
        game=fake_campaign["game"],
        campaign_name=fake_campaign["campaign_name"],
        source=fake_campaign["source"],
        starts_at=fake_campaign["starts_at"],
        ends_at=fake_campaign["ends_at"],
        confidence=fake_campaign["confidence"],
    )

    # Send test notification
    sent = await notification_service.send_stage_notification(
        bot=context.application.bot,
        state=state,
        campaign=fake_campaign,
        stage="live",
    )

    await update.message.reply_text(
        f"✅ Test sent to {sent} subscriber(s).\n"
        f"Stage: live\n"
        f"Game: Rust\n"
        f"Check /status to see the fake campaign."
    )

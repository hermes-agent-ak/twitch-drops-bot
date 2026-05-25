"""/status command — show active drop campaigns."""

import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("twitch-drops-bot.handlers.status")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active drop campaigns."""
    state = context.application.bot_data["state"]
    campaigns = state.get_active_campaigns()

    if not campaigns:
        await update.message.reply_text(
            "No active drop campaigns right now.\n"
            "I'll notify you when new ones appear!"
        )
        return

    lines = ["<b>🎁 Active Twitch Drops</b>\n"]
    for c in campaigns:
        start = datetime.fromtimestamp(c["starts_at"], tz=timezone.utc)
        end = datetime.fromtimestamp(c["ends_at"], tz=timezone.utc)
        lines.append(
            f"• <b>{c['game']}</b> — {c['campaign_name']}\n"
            f"  {start.strftime('%Y-%m-%d %H:%M')} → "
            f"{end.strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"  Confidence: {c['confidence']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

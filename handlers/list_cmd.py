"""/list command — show current subscriptions."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("twitch-drops-bot.handlers.list")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List current subscriptions."""
    state = context.application.bot_data["state"]
    chat_id = update.effective_chat.id
    games = state.get_user_games(chat_id)

    if games:
        await update.message.reply_text(
            f"Your subscriptions: <b>{', '.join(games)}</b>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "No subscriptions. Use /subscribe &lt;game&gt; to get started."
        )

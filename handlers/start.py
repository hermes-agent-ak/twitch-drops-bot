"""/start command — welcome message and available commands."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("twitch-drops-bot.handlers.start")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and available commands."""
    state = context.application.bot_data["state"]
    chat_id = update.effective_chat.id
    username = (
        update.effective_user.username
        or update.effective_user.first_name
        or "unknown"
    )
    state.add_user(chat_id, username)

    games = state.get_user_games(chat_id) or ["none"]
    await update.message.reply_text(
        f"🎮 <b>Twitch Drops Bot</b>\n\n"
        f"Hi {username}! I monitor Twitch Drops and notify you when "
        f"new campaigns are detected.\n\n"
        f"<b>Your subscriptions:</b> {', '.join(games)}\n\n"
        f"<b>Commands:</b>\n"
        f"/subscribe &lt;game&gt; — Get drop alerts\n"
        f"/unsubscribe &lt;game&gt; — Stop alerts\n"
        f"/list — Show your subscriptions\n"
        f"/status — Active campaigns\n"
        f"/health — Source health\n\n"
        f"Start: /subscribe Rust",
        parse_mode="HTML",
    )

"""/subscribe command — subscribe to drop alerts for a game."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("twitch-drops-bot.handlers.subscribe")

KNOWN_GAMES = ["Rust"]


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to drop alerts for a game."""
    state = context.application.bot_data["state"]
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        await update.message.reply_text(
            f"Usage: /subscribe &lt;game&gt;\nAvailable: {', '.join(KNOWN_GAMES)}"
        )
        return

    game = " ".join(args)
    if game not in KNOWN_GAMES:
        await update.message.reply_text(
            f"Unknown game: {game}\nAvailable: {', '.join(KNOWN_GAMES)}"
        )
        return

    current = state.get_user_games(chat_id)
    if game in current:
        await update.message.reply_text(
            f"You're already subscribed to {game}!"
        )
        return

    current.append(game)
    state.update_user_games(chat_id, current)
    await update.message.reply_text(
        f"✅ Subscribed to <b>{game}</b>!\n"
        f"You'll get notified when new Twitch Drops are detected.",
        parse_mode="HTML",
    )

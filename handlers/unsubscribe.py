"""/unsubscribe command — stop drop alerts for a game."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("twitch-drops-bot.handlers.unsubscribe")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from drop alerts."""
    state = context.application.bot_data["state"]
    chat_id = update.effective_chat.id
    args = context.args
    current = state.get_user_games(chat_id)

    if not args:
        if not current:
            await update.message.reply_text("You're not subscribed to any games.")
            return
        await update.message.reply_text(
            f"Your subscriptions: {', '.join(current)}\n"
            f"Usage: /unsubscribe &lt;game&gt;"
        )
        return

    game = " ".join(args)
    if game not in current:
        await update.message.reply_text(
            f"You're not subscribed to {game}.\n"
            f"Subscriptions: {', '.join(current) if current else 'none'}"
        )
        return

    current.remove(game)
    if current:
        state.update_user_games(chat_id, current)
    else:
        state.deactivate_user(chat_id)

    await update.message.reply_text(
        f"❌ Unsubscribed from <b>{game}</b>.", parse_mode="HTML"
    )

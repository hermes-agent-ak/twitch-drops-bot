"""/health command — source health status."""

import logging
import sqlite3
from telegram import Update
from telegram.ext import ContextTypes
from config import DB_PATH

logger = logging.getLogger("twitch-drops-bot.handlers.health")


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show source health status."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM source_health").fetchall()

    if not rows:
        await update.message.reply_text("No health data yet. Check back later.")
        return

    status_icon = {"ok": "✅", "degraded": "⚠️", "failed": "🔴"}
    lines = ["<b>🏥 Source Health</b>\n"]
    for r in rows:
        icon = status_icon.get(r["status"], "❓")
        lines.append(
            f"{icon} <b>{r['source_name']}</b>: {r['status']}\n"
            f"  Failures: {r['consecutive_failures']}"
        )
        if r["last_error"]:
            lines.append(f"  Error: {r['last_error'][:100]}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

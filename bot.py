#!/usr/bin/env python3
"""Twitch Drops Telegram Bot.

Monitors Twitch Drops for games (starting with Rust) and notifies
subscribed Telegram users when new campaigns are detected.

Usage:
    python bot.py

Requirements:
    TELEGRAM_BOT_TOKEN in .env (get from @BotFather with /newbot)
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from sources.facepunch import FacepunchScraper
from sources.steam_news import SteamNewsChecker
from state import StateManager
from engine import ConfidenceEngine
from health import HealthMonitor
from config import (
    POLL_INTERVAL_MINUTES,
    TELEGRAM_BOT_TOKEN,
    ADMIN_CHAT_ID,
    FACEPUNCH_URL_MAP,
    STEAM_GAME_MAP,
)

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("twitch-drops-bot")

# --- Global state ---
state = StateManager()
health_monitor = HealthMonitor(state)
confidence_engine = ConfidenceEngine()

# Sources
SOURCES = {
    "facepunch": FacepunchScraper(),
    "steam_news": SteamNewsChecker(),
}

KNOWN_GAMES = sorted(
    set(FACEPUNCH_URL_MAP.values()) | set(STEAM_GAME_MAP.values())
)


# ─── Telegram Commands ────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message and available commands."""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name or "unknown"

    state.add_user(chat_id, username)

    games_list = ", ".join(KNOWN_GAMES)
    await update.message.reply_text(
        f"🎮 <b>Twitch Drops Bot</b>\n\n"
        f"Hi {username}! I monitor Twitch Drops and notify you when "
        f"new campaigns are detected.\n\n"
        f"<b>Available games:</b> {games_list}\n\n"
        f"<b>Commands:</b>\n"
        f"/subscribe &lt;game&gt; — Get drop alerts for a game\n"
        f"/unsubscribe &lt;game&gt; — Stop alerts for a game\n"
        f"/list — Show your subscriptions\n"
        f"/status — Show active drop campaigns\n"
        f"/health — Check source health\n\n"
        f"Start with: /subscribe Rust",
        parse_mode="HTML",
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to drop alerts for a game."""
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        games_list = ", ".join(KNOWN_GAMES)
        await update.message.reply_text(
            f"Usage: /subscribe &lt;game&gt;\n"
            f"Available: {games_list}"
        )
        return

    game = " ".join(args)
    if game not in KNOWN_GAMES:
        await update.message.reply_text(
            f"Unknown game: {game}\n"
            f"Available: {', '.join(KNOWN_GAMES)}"
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


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from drop alerts."""
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
            f"Your subscriptions: {', '.join(current) if current else 'none'}"
        )
        return

    current.remove(game)
    if current:
        state.update_user_games(chat_id, current)
    else:
        state.deactivate_user(chat_id)

    await update.message.reply_text(f"❌ Unsubscribed from <b>{game}</b>.", parse_mode="HTML")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List current subscriptions."""
    chat_id = update.effective_chat.id
    games = state.get_user_games(chat_id)

    if games:
        await update.message.reply_text(
            f"Your subscriptions: <b>{', '.join(games)}</b>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "You're not subscribed to any games.\n"
            "Use /subscribe &lt;game&gt; to get started."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active drop campaigns."""
    campaigns = state.get_active_campaigns()

    if not campaigns:
        await update.message.reply_text(
            "No active drop campaigns detected right now.\n"
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

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show source health status."""
    import sqlite3
    from config import DB_PATH

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM source_health"
        ).fetchall()

    if not rows:
        await update.message.reply_text("No health data yet. Check back later.")
        return

    lines = ["<b>🏥 Source Health</b>\n"]
    for r in rows:
        status_icon = {"ok": "✅", "degraded": "⚠️", "failed": "🔴"}
        icon = status_icon.get(r["status"], "❓")
        lines.append(
            f"{icon} <b>{r['source_name']}</b>: {r['status']}\n"
            f"  Failures: {r['consecutive_failures']}"
        )
        if r["last_error"]:
            lines.append(f"  Error: {r['last_error'][:100]}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ─── Scheduler ────────────────────────────────────────────────────


async def poll_sources():
    """Poll all sources, update state, send notifications."""
    logger.info("Polling sources...")

    # Fetch all sources in parallel
    all_campaigns = []
    source_errors = {}

    tasks = {}
    for name, source in SOURCES.items():
        tasks[name] = asyncio.create_task(source.fetch())

    for name, task in tasks.items():
        try:
            campaigns = await task
            all_campaigns.extend(campaigns)
            await health_monitor.record_success(name)
            logger.info(
                "Source %s: %d campaigns found", name, len(campaigns)
            )
        except Exception as e:
            source_errors[name] = str(e)
            await health_monitor.record_failure(name, str(e))
            logger.error("Source %s failed: %s", name, e)

    # Confidence scoring
    scored = confidence_engine.score(all_campaigns)

    # Upsert campaigns and detect new HIGH-confidence ones
    new_high_confidence = []
    for campaign, confidence in scored:
        campaign_id = campaign.compute_id()
        is_new = state.upsert_campaign(
            campaign_id=campaign_id,
            game=campaign.game,
            campaign_name=campaign.campaign_name,
            source=campaign.source,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            confidence=confidence,
        )
        if is_new and confidence == "HIGH":
            new_high_confidence.append(campaign)

    # Send notifications for new HIGH-confidence campaigns
    if new_high_confidence:
        await notify_users(new_high_confidence)

    logger.info(
        "Poll complete: %d campaigns (%d new HIGH), %d errors",
        len(scored), len(new_high_confidence), len(source_errors),
    )


async def notify_users(campaigns: list):
    """Send Telegram notifications to subscribed users."""
    # We need the bot application reference for sending messages
    # This will be set up in main()
    pass  # Implemented inline in the scheduler loop


# ─── Main ─────────────────────────────────────────────────────────


async def scheduler_loop(app: Application):
    """Periodically poll sources and notify users."""
    while True:
        try:
            await poll_and_notify(app)
        except Exception as e:
            logger.error("Scheduler error: %s", e, exc_info=True)

        await asyncio.sleep(POLL_INTERVAL_MINUTES * 60)


async def poll_and_notify(app: Application):
    """Poll sources and send notifications via the bot app."""
    logger.info("Polling sources...")

    all_campaigns = []
    for name, source in SOURCES.items():
        try:
            campaigns = await source.fetch()
            all_campaigns.extend(campaigns)
            await health_monitor.record_success(name)
            logger.info("Source %s: %d campaigns found", name, len(campaigns))
        except Exception as e:
            await health_monitor.record_failure(name, str(e))
            logger.error("Source %s failed: %s", name, e)

    scored = confidence_engine.score(all_campaigns)

    new_high = []
    for campaign, confidence in scored:
        campaign_id = campaign.compute_id()
        is_new = state.upsert_campaign(
            campaign_id=campaign_id,
            game=campaign.game,
            campaign_name=campaign.campaign_name,
            source=campaign.source,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            confidence=confidence,
        )
        if is_new and confidence == "HIGH":
            new_high.append(campaign)

    # Notify subscribed users
    for campaign_data in new_high:
        chat_ids = state.get_subscribed_users(campaign_data.game)

        if not chat_ids:
            logger.info(
                "No users subscribed to %s, skipping notification",
                campaign_data.game,
            )
            continue

        start = datetime.fromtimestamp(campaign_data.starts_at, tz=timezone.utc)
        end = datetime.fromtimestamp(campaign_data.ends_at, tz=timezone.utc)

        msg = (
            f"🎁 <b>New Twitch Drops!</b>\n\n"
            f"Game: <b>{campaign_data.game}</b>\n"
            f"Campaign: {campaign_data.campaign_name}\n"
            f"Start: {start.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"End: {end.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Confidence: HIGH ✅\n"
            f"Sources: facepunch + steam_news"
        )

        for chat_id in chat_ids:
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                )
                logger.info(
                    "Notified %s about %s drops",
                    chat_id, campaign_data.game,
                )
            except Exception as e:
                logger.error(
                    "Failed to notify %s: %s", chat_id, e
                )

        # Mark as notified
        campaign_id = campaign_data.compute_id()
        state.mark_notified(campaign_id)

    # Health alerts to admin
    unhealthy = state.get_unhealthy_sources(3)
    if unhealthy and ADMIN_CHAT_ID:
        admin_id = int(ADMIN_CHAT_ID)
        for src in unhealthy:
            await app.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"⚠️ <b>Source Health Alert</b>\n"
                    f"Source: {src['source_name']}\n"
                    f"Failures: {src['consecutive_failures']}\n"
                    f"Error: {src.get('last_error', 'unknown')[:200]}"
                ),
                parse_mode="HTML",
            )


async def main():
    """Start the bot and scheduler."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN not set! "
            "Copy .env.example to .env and add your token from @BotFather"
        )
        sys.exit(1)

    logger.info(
        "Starting Twitch Drops Bot — monitoring: %s",
        ", ".join(KNOWN_GAMES),
    )

    # Build Telegram app
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("health", cmd_health))

    # Start scheduler in background
    scheduler_task = asyncio.create_task(scheduler_loop(app))
    logger.info("Scheduler started (every %d minutes)", POLL_INTERVAL_MINUTES)

    # Start bot
    logger.info("Bot polling started")
    await app.run_polling()

    scheduler_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Twitch Drops Telegram Bot.

Monitors Twitch Drops for games (starting with Rust) and notifies
subscribed Telegram users when new campaigns are detected.

Usage:
    python bot.py

Requirements:
    TELEGRAM_BOT_TOKEN in .env (get from @BotFather with /newbot)
"""

from dotenv import load_dotenv
load_dotenv()

import logging  # noqa: E402
import sys  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from telegram import Update  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CommandHandler,
    ContextTypes,
)

from sources.facepunch import FacepunchScraper  # noqa: E402
from sources.steam_news import SteamNewsChecker  # noqa: E402
from state import StateManager  # noqa: E402
from engine import ConfidenceEngine  # noqa: E402
from health import HealthMonitor  # noqa: E402
from config import (  # noqa: E402
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


# ─── Notification Messages ────────────────────────────────────────

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

# ─── Scheduler ────────────────────────────────────────────────────


async def poll_and_notify(app: Application):
    """Poll sources, update state, and send stage-based notifications."""
    logger.info("Polling sources...")

    # 1. Fetch all sources
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

    # 2. Confidence scoring + upsert into DB
    scored = confidence_engine.score(all_campaigns)
    for campaign, confidence in scored:
        state.upsert_campaign(
            campaign_id=campaign.compute_id(),
            game=campaign.game,
            campaign_name=campaign.campaign_name,
            source=campaign.source,
            starts_at=campaign.starts_at,
            ends_at=campaign.ends_at,
            confidence=confidence,
        )

    # 3. Find campaigns that need a notification at their current stage
    due = state.get_campaigns_needing_notification()

    for campaign in due:
        next_stage = campaign["_next_stage"]
        game = campaign["game"]
        chat_ids = state.get_subscribed_users(game)

        if not chat_ids:
            logger.info("No subscribers for %s, skipping %s", game, next_stage)
            state.advance_stage(campaign["id"], next_stage)
            continue

        # Build notification message
        start_dt = datetime.fromtimestamp(campaign["starts_at"], tz=timezone.utc)
        end_dt = datetime.fromtimestamp(campaign["ends_at"], tz=timezone.utc)
        conf_label = CONFIDENCE_LABELS.get(campaign["confidence"], campaign["confidence"])

        msg = STAGE_MESSAGES[next_stage].format(
            game=game,
            name=campaign["campaign_name"],
            start=start_dt.strftime("%Y-%m-%d %H:%M UTC"),
            end=end_dt.strftime("%Y-%m-%d %H:%M UTC"),
            confidence=conf_label,
        )

        # Send to all subscribers
        for chat_id in chat_ids:
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                )
                logger.info("Sent '%s' for %s to %s", next_stage, game, chat_id)
            except Exception as e:
                logger.error("Failed to notify %s: %s", chat_id, e)

        # Advance to next stage
        state.advance_stage(campaign["id"], next_stage)

    logger.info(
        "Poll complete: %d campaigns scored, %d notifications sent",
        len(scored), len(due),
    )

    # 4. Health alerts to admin
    unhealthy = state.get_unhealthy_sources(3)
    if unhealthy and ADMIN_CHAT_ID:
        try:
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
        except ValueError:
            logger.warning("Invalid ADMIN_CHAT_ID: %s", ADMIN_CHAT_ID)


def main():
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

    # Schedule the poll loop via job_queue
    app.job_queue.run_repeating(
        poll_and_notify_wrapper,
        interval=POLL_INTERVAL_MINUTES * 60,
        first=5,
    )
    logger.info("Scheduler started (every %d minutes)", POLL_INTERVAL_MINUTES)

    # run_polling() is synchronous — creates and manages its own event loop
    logger.info("Bot polling started")
    app.run_polling()


async def poll_and_notify_wrapper(context):
    """Wrapper for job_queue callback."""
    await poll_and_notify(context.application)


if __name__ == "__main__":
    main()

"""Configuration for the Twitch Drops Telegram Bot."""

import os

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN_RUST", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

# --- Polling ---
POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "15"))

# --- Game Mappings ---

# Steam appid → game name
STEAM_GAME_MAP: dict[int, str] = {
    252490: "Rust",
}

# Facepunch (publisher) URL → game name
FACEPUNCH_URL_MAP: dict[str, str] = {
    "https://twitch.facepunch.com/": "Rust",
}

# Drop keywords for Steam news filtering (case-insensitive matching)
DROP_KEYWORDS: list[str] = [
    "twitch drops",
    "twitch drop",
    "drop campaign",
    "#drops",
    "new drops",
    "drops event",
    "drops are live",
]

# --- Health ---
HEALTH_FAILURE_THRESHOLD = 3  # consecutive failures before alert

# --- Database ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drops.db")

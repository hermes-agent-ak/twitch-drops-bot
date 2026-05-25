# Twitch Drops Telegram Bot 🎮

Monitor Twitch Drops for specific games and get notified via Telegram
when new drop campaigns are detected.

**Currently supports:** Rust (via twitch.facepunch.com + Steam News API)

## How It Works

The bot checks multiple sources every 15 minutes:

1. **twitch.facepunch.com** (PRIMARY) — Publisher-hosted drops page, public, no login
2. **Steam News API** (CONFIRMATION) — Official Valve API, no auth

When both sources agree → HIGH confidence notification is sent.

## Setup (5 minutes)

### 1. Create a new Telegram Bot

**IMPORTANT: Create a NEW bot. Do not reuse an existing bot token.**

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g. `My Twitch Drops Bot`)
4. Choose a username (must end with `bot`, e.g. `my_twitch_drops_bot`)
5. **Copy the token** — looks like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Configure the bot

```bash
# Clone the repo
git clone https://github.com/hermes-agent-ak/twitch-drops-bot.git
cd twitch-drops-bot

# Create .env from example
cp .env.example .env

# Edit .env and paste your token:
# TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
nano .env
```

### 3. Install and run

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

### 4. Subscribe to alerts

1. Open Telegram and find your bot (by the username you chose)
2. Send `/start`
3. Send `/subscribe Rust`

That's it! You'll get notified when new Rust Twitch Drops are detected.

## Deploy as a Service (optional)

```bash
# Install the systemd user service
mkdir -p ~/.config/systemd/user
cp deploy/twitch-drops-bot.service ~/.config/systemd/user/

# Edit the service if your paths differ
nano ~/.config/systemd/user/twitch-drops-bot.service

# Enable and start
systemctl --user daemon-reload
systemctl --user enable twitch-drops-bot
systemctl --user start twitch-drops-bot

# Check status
systemctl --user status twitch-drops-bot

# View logs
journalctl --user -u twitch-drops-bot -f
```

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and setup |
| `/subscribe <game>` | Get alerts for a game |
| `/unsubscribe <game>` | Stop alerts for a game |
| `/list` | Show your subscriptions |
| `/status` | Show active drop campaigns |
| `/health` | Check source health |

## Adding More Games

Edit `config.py`:

```python
# Add Steam appid → game name
STEAM_GAME_MAP = {
    252490: "Rust",
    123456: "Your Game Here",
}

# Add publisher drops page URL → game name
FACEPUNCH_URL_MAP = {
    "https://twitch.facepunch.com/": "Rust",
    # Add more publisher pages here
}
```

## Architecture

```
sources/        → Scrapers (facepunch + steam_news)
state/          → SQLite persistence
engine/         → Confidence scoring
health/         → Source monitoring
bot.py          → Telegram bot + scheduler
```

## Requirements

- Python 3.11+
- Telegram Bot Token (from @BotFather)
- No Twitch account needed
- No API keys needed (Steam API is public)

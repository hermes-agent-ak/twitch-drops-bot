"""SQLite state manager for campaigns, users, and source health."""

import json
import logging
import sqlite3
import time

from config import DB_PATH

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    game TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    source TEXT NOT NULL,
    starts_at INTEGER NOT NULL,
    ends_at INTEGER NOT NULL DEFAULT 0,
    confidence TEXT NOT NULL DEFAULT 'LOW',
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    notification_stage TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    subscribed_games TEXT NOT NULL DEFAULT '["Rust"]',
    created_at INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS source_health (
    source_name TEXT PRIMARY KEY,
    last_success INTEGER,
    last_failure INTEGER,
    consecutive_failures INTEGER DEFAULT 0,
    last_error TEXT,
    status TEXT DEFAULT 'ok'
);
"""

# Notification stages in order
STAGES = ["announced", "reminder_24h", "live", "ending_soon"]


class StateManager:
    """Manages persistent state in SQLite."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DB_PATH
        self._init_db()
        self._migrate()

    def _init_db(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _migrate(self):
        """Migrate old schema: 'notified' column → 'notification_stage'."""
        with sqlite3.connect(self.db_path) as conn:
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(campaigns)"
            ).fetchall()]

            if "notified" in cols and "notification_stage" not in cols:
                logger.info("Migrating: notified → notification_stage")
                conn.execute(
                    "ALTER TABLE campaigns ADD COLUMN notification_stage TEXT DEFAULT NULL"
                )
                # Convert old notified=1 → stage='live' (best guess: it was already active)
                conn.execute(
                    "UPDATE campaigns SET notification_stage = 'live' WHERE notified = 1"
                )
                conn.commit()
                logger.info("Migration complete")

    # --- Campaigns ---

    def upsert_campaign(
        self,
        campaign_id: str,
        game: str,
        campaign_name: str,
        source: str,
        starts_at: int,
        ends_at: int,
        confidence: str,
    ) -> bool:
        """Insert or update a campaign. Returns True if it's new."""
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id, notification_stage FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE campaigns
                       SET last_seen = ?, confidence = ?, ends_at = ?
                       WHERE id = ?""",
                    (now, confidence, ends_at, campaign_id),
                )
                conn.commit()
                return False  # already existed
            else:
                conn.execute(
                    """INSERT INTO campaigns
                       (id, game, campaign_name, source, starts_at,
                        ends_at, confidence, first_seen, last_seen, notification_stage)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
                    (
                        campaign_id, game, campaign_name, source,
                        starts_at, ends_at, confidence, now, now,
                    ),
                )
                conn.commit()
                return True  # new campaign

    def advance_stage(self, campaign_id: str, stage: str):
        """Advance a campaign to the next notification stage."""
        if stage not in STAGES:
            raise ValueError(f"Invalid stage: {stage}")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE campaigns SET notification_stage = ? WHERE id = ?",
                (stage, campaign_id),
            )
            conn.commit()

    def get_campaigns_needing_notification(self) -> list[dict]:
        """Get campaigns that are due for a notification at their current stage.

        Logic:
        - NULL stage + any time → needs 'announced'
        - 'announced' + within 24h of start → needs 'reminder_24h'
        - 'reminder_24h' + past start → needs 'live'
        - 'live' + within 24h of end → needs 'ending_soon'
        - 'ending_soon' → done, no more notifications
        - If campaign ended (ends_at < now) → skip entirely
        """
        now = int(time.time())
        results = []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE ends_at > ?",
                (now,),
            ).fetchall()

        for row in rows:
            campaign = dict(row)
            stage = campaign.get("notification_stage")
            starts_at = campaign["starts_at"]
            ends_at = campaign["ends_at"]

            if stage is None:
                # New campaign — announce immediately
                campaign["_next_stage"] = "announced"
                results.append(campaign)

            elif stage == "announced" and now >= starts_at - 86400:
                # Within 24h of start — send reminder
                campaign["_next_stage"] = "reminder_24h"
                results.append(campaign)

            elif stage == "reminder_24h" and now >= starts_at:
                # Campaign has started — send live notification
                campaign["_next_stage"] = "live"
                results.append(campaign)

            elif stage == "live" and now >= ends_at - 86400:
                # Within 24h of end — send ending soon
                campaign["_next_stage"] = "ending_soon"
                results.append(campaign)

            # 'ending_soon' → no more notifications
            # Campaigns that aren't due yet → skip

        return results

    def get_active_campaigns(self, game: str | None = None) -> list[dict]:
        """Get campaigns that haven't ended yet."""
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if game:
                rows = conn.execute(
                    "SELECT * FROM campaigns WHERE ends_at > ? AND game = ?",
                    (now, game),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM campaigns WHERE ends_at > ?",
                    (now,),
                ).fetchall()
            return [dict(r) for r in rows]

    # --- Users ---

    def add_user(self, chat_id: int, username: str = "") -> bool:
        """Add a new user. Returns True if new, False if already exists."""
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """INSERT INTO users (chat_id, username, created_at)
                       VALUES (?, ?, ?)""",
                    (chat_id, username, now),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.execute(
                    "UPDATE users SET is_active = 1 WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
                return False

    def get_subscribed_users(self, game: str) -> list[int]:
        """Get chat_ids of users subscribed to a game."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT chat_id, subscribed_games FROM users
                   WHERE is_active = 1"""
            ).fetchall()

            chat_ids = []
            for chat_id, games_json in rows:
                try:
                    games = json.loads(games_json)
                except (json.JSONDecodeError, TypeError):
                    games = ["Rust"]
                if game in games:
                    chat_ids.append(chat_id)
            return chat_ids

    def get_user_games(self, chat_id: int) -> list[str]:
        """Get games a user is subscribed to."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT subscribed_games FROM users WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if not row:
                return []
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return []

    def update_user_games(self, chat_id: int, games: list[str]):
        """Update a user's subscribed games."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET subscribed_games = ? WHERE chat_id = ?",
                (json.dumps(games), chat_id),
            )
            conn.commit()

    def deactivate_user(self, chat_id: int):
        """Deactivate a user (unsubscribe all)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET is_active = 0 WHERE chat_id = ?",
                (chat_id,),
            )
            conn.commit()

    # --- Health ---

    def record_success(self, source_name: str):
        """Record a successful source check."""
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO source_health
                   (source_name, last_success, consecutive_failures, status)
                   VALUES (?, ?, 0, 'ok')
                   ON CONFLICT(source_name) DO UPDATE SET
                   last_success = ?, consecutive_failures = 0,
                   status = 'ok', last_error = NULL""",
                (source_name, now, now),
            )
            conn.commit()

    def record_failure(self, source_name: str, error: str):
        """Record a failed source check."""
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO source_health
                   (source_name, last_failure, consecutive_failures,
                    last_error, status)
                   VALUES (?, ?, 1, ?, 'degraded')
                   ON CONFLICT(source_name) DO UPDATE SET
                   last_failure = ?,
                   consecutive_failures = consecutive_failures + 1,
                   last_error = ?,
                   status = CASE
                       WHEN consecutive_failures + 1 >= 3 THEN 'failed'
                       ELSE 'degraded'
                   END""",
                (source_name, now, error, now, error),
            )
            conn.commit()

    def get_unhealthy_sources(self, threshold: int = 3) -> list[dict]:
        """Get sources that have failed too many times."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM source_health
                   WHERE consecutive_failures >= ?""",
                (threshold,),
            ).fetchall()
            return [dict(r) for r in rows]

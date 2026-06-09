"""SQLite storage backend (async via aiosqlite).

Used for local development when no DATABASE_URL is configured. Note: on ephemeral hosts
(e.g. Replit Deployments) the SQLite file is wiped on redeploy — set DATABASE_URL to use
the Postgres backend instead. See storage/db.py for backend selection.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import aiosqlite

from config import settings
from storage.models import Account

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id           INTEGER PRIMARY KEY,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    created_at            TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER NOT NULL,
    email           TEXT    NOT NULL,
    creds_enc       BLOB    NOT NULL,
    last_history_id TEXT,
    created_at      TEXT    NOT NULL,
    UNIQUE (telegram_id, email)
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state         TEXT PRIMARY KEY,
    telegram_id   INTEGER NOT NULL,
    code_verifier TEXT,
    created_at    TEXT    NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(_SCHEMA)
        # Migration: add code_verifier to oauth_states for DBs created before PKCE support.
        try:
            await db.execute("ALTER TABLE oauth_states ADD COLUMN code_verifier TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        await db.commit()


# ---- users -----------------------------------------------------------------
async def ensure_user(telegram_id: int) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, created_at) VALUES (?, ?)",
            (telegram_id, _now()),
        )
        await db.commit()


async def get_notifications_enabled(telegram_id: int) -> bool:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT notifications_enabled FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
    return bool(row[0]) if row else True


async def set_notifications_enabled(telegram_id: int, enabled: bool) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "UPDATE users SET notifications_enabled = ? WHERE telegram_id = ?",
            (1 if enabled else 0, telegram_id),
        )
        await db.commit()


# ---- oauth states ----------------------------------------------------------
async def create_oauth_state(
    state: str, telegram_id: int, code_verifier: str | None
) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "INSERT INTO oauth_states (state, telegram_id, code_verifier, created_at) "
            "VALUES (?, ?, ?, ?)",
            (state, telegram_id, code_verifier, _now()),
        )
        await db.commit()


async def pop_oauth_state(state: str) -> tuple[int, str | None] | None:
    """Return (telegram_id, code_verifier) for a state token and delete it (single use)."""
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT telegram_id, code_verifier FROM oauth_states WHERE state = ?",
            (state,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        await db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        await db.commit()
        return int(row[0]), row[1]


# ---- accounts --------------------------------------------------------------
async def upsert_account(
    telegram_id: int, email: str, creds_enc: bytes, last_history_id: str | None
) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """
            INSERT INTO accounts (telegram_id, email, creds_enc, last_history_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id, email) DO UPDATE SET
                creds_enc       = excluded.creds_enc,
                last_history_id = excluded.last_history_id
            """,
            (telegram_id, email, creds_enc, last_history_id, _now()),
        )
        await db.commit()


async def get_accounts(telegram_id: int) -> list[Account]:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT id, telegram_id, email, creds_enc, last_history_id "
            "FROM accounts WHERE telegram_id = ? ORDER BY email",
            (telegram_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [Account(*row) for row in rows]


async def get_account_by_id(account_id: int) -> Account | None:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT id, telegram_id, email, creds_enc, last_history_id "
            "FROM accounts WHERE id = ?",
            (account_id,),
        ) as cur:
            row = await cur.fetchone()
    return Account(*row) if row else None


async def get_all_accounts() -> list[Account]:
    async with aiosqlite.connect(settings.db_path) as db:
        async with db.execute(
            "SELECT id, telegram_id, email, creds_enc, last_history_id FROM accounts"
        ) as cur:
            rows = await cur.fetchall()
    return [Account(*row) for row in rows]


async def update_credentials(account_id: int, creds_enc: bytes) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "UPDATE accounts SET creds_enc = ? WHERE id = ?", (creds_enc, account_id)
        )
        await db.commit()


async def update_history_id(account_id: int, history_id: str) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "UPDATE accounts SET last_history_id = ? WHERE id = ?",
            (history_id, account_id),
        )
        await db.commit()


async def delete_account(account_id: int) -> None:
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()

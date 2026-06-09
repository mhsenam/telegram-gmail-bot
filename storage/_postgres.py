"""PostgreSQL storage backend (async via asyncpg).

Used when DATABASE_URL is set (e.g. Replit PostgreSQL, Neon, Supabase, RDS). Unlike the
SQLite file, this survives redeploys, so connected accounts persist. Same public API as the
SQLite backend; storage/db.py picks one at import time.
"""
from __future__ import annotations

import asyncio

import asyncpg

from config import settings
from storage.models import Account

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id           BIGINT      PRIMARY KEY,
    notifications_enabled BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
    id              BIGSERIAL   PRIMARY KEY,
    telegram_id     BIGINT      NOT NULL,
    email           TEXT        NOT NULL,
    creds_enc       BYTEA       NOT NULL,
    last_history_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (telegram_id, email)
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state         TEXT        PRIMARY KEY,
    telegram_id   BIGINT      NOT NULL,
    code_verifier TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    dsn=settings.database_url, min_size=1, max_size=5
                )
    return _pool


async def init_db() -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA)
        # Idempotent migration for pre-existing DBs without the PKCE column.
        await conn.execute(
            "ALTER TABLE oauth_states ADD COLUMN IF NOT EXISTS code_verifier TEXT"
        )


def _account(row: asyncpg.Record) -> Account:
    return Account(
        id=row["id"],
        telegram_id=row["telegram_id"],
        email=row["email"],
        creds_enc=bytes(row["creds_enc"]),
        last_history_id=row["last_history_id"],
    )


# ---- users -----------------------------------------------------------------
async def ensure_user(telegram_id: int) -> None:
    pool = await _get_pool()
    await pool.execute(
        "INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT (telegram_id) DO NOTHING",
        telegram_id,
    )


async def get_notifications_enabled(telegram_id: int) -> bool:
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT notifications_enabled FROM users WHERE telegram_id = $1", telegram_id
    )
    return bool(row[0]) if row else True


async def set_notifications_enabled(telegram_id: int, enabled: bool) -> None:
    pool = await _get_pool()
    await pool.execute(
        "UPDATE users SET notifications_enabled = $1 WHERE telegram_id = $2",
        enabled,
        telegram_id,
    )


# ---- oauth states ----------------------------------------------------------
async def create_oauth_state(
    state: str, telegram_id: int, code_verifier: str | None
) -> None:
    pool = await _get_pool()
    await pool.execute(
        "INSERT INTO oauth_states (state, telegram_id, code_verifier) VALUES ($1, $2, $3)",
        state,
        telegram_id,
        code_verifier,
    )


async def pop_oauth_state(state: str) -> tuple[int, str | None] | None:
    """Return (telegram_id, code_verifier) and delete it atomically (single use)."""
    pool = await _get_pool()
    row = await pool.fetchrow(
        "DELETE FROM oauth_states WHERE state = $1 RETURNING telegram_id, code_verifier",
        state,
    )
    if row is None:
        return None
    return int(row[0]), row[1]


# ---- accounts --------------------------------------------------------------
async def upsert_account(
    telegram_id: int, email: str, creds_enc: bytes, last_history_id: str | None
) -> None:
    pool = await _get_pool()
    await pool.execute(
        """
        INSERT INTO accounts (telegram_id, email, creds_enc, last_history_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (telegram_id, email) DO UPDATE SET
            creds_enc       = EXCLUDED.creds_enc,
            last_history_id = EXCLUDED.last_history_id
        """,
        telegram_id,
        email,
        creds_enc,
        last_history_id,
    )


async def get_accounts(telegram_id: int) -> list[Account]:
    pool = await _get_pool()
    rows = await pool.fetch(
        "SELECT id, telegram_id, email, creds_enc, last_history_id "
        "FROM accounts WHERE telegram_id = $1 ORDER BY email",
        telegram_id,
    )
    return [_account(r) for r in rows]


async def get_account_by_id(account_id: int) -> Account | None:
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT id, telegram_id, email, creds_enc, last_history_id "
        "FROM accounts WHERE id = $1",
        account_id,
    )
    return _account(row) if row else None


async def get_all_accounts() -> list[Account]:
    pool = await _get_pool()
    rows = await pool.fetch(
        "SELECT id, telegram_id, email, creds_enc, last_history_id FROM accounts"
    )
    return [_account(r) for r in rows]


async def update_credentials(account_id: int, creds_enc: bytes) -> None:
    pool = await _get_pool()
    await pool.execute(
        "UPDATE accounts SET creds_enc = $1 WHERE id = $2", creds_enc, account_id
    )


async def update_history_id(account_id: int, history_id: str) -> None:
    pool = await _get_pool()
    await pool.execute(
        "UPDATE accounts SET last_history_id = $1 WHERE id = $2", history_id, account_id
    )


async def delete_account(account_id: int) -> None:
    pool = await _get_pool()
    await pool.execute("DELETE FROM accounts WHERE id = $1", account_id)

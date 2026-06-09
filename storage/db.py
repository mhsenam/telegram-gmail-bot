"""Storage facade — picks a backend at import time and re-exports its API.

  - DATABASE_URL set   -> PostgreSQL (asyncpg). Persists across redeploys (use in production
                          / on Replit). Recommended for any public deployment.
  - DATABASE_URL unset -> SQLite (aiosqlite). Zero-config local development.

The rest of the app imports from `storage.db` and is unaware of which backend is active —
both expose identical functions and the shared `Account` type.

Tables (both backends)
----------------------
users        : one row per Telegram user + their preferences
accounts     : one row per connected Gmail account (encrypted creds + sync cursor)
oauth_states : short-lived CSRF tokens linking an in-progress OAuth flow to a user
"""
from __future__ import annotations

import logging

from config import settings
from storage.models import Account  # re-exported for callers (e.g. `from storage.db import Account`)

log = logging.getLogger(__name__)

if settings.database_url:
    from storage import _postgres as _backend

    log.info("Storage backend: PostgreSQL")
else:
    from storage import _sqlite as _backend

    log.info("Storage backend: SQLite (%s)", settings.db_path)

# Re-export the backend's API unchanged.
init_db = _backend.init_db
ensure_user = _backend.ensure_user
get_notifications_enabled = _backend.get_notifications_enabled
set_notifications_enabled = _backend.set_notifications_enabled
create_oauth_state = _backend.create_oauth_state
pop_oauth_state = _backend.pop_oauth_state
upsert_account = _backend.upsert_account
get_accounts = _backend.get_accounts
get_account_by_id = _backend.get_account_by_id
get_all_accounts = _backend.get_all_accounts
update_credentials = _backend.update_credentials
update_history_id = _backend.update_history_id
delete_account = _backend.delete_account

__all__ = [
    "Account",
    "init_db",
    "ensure_user",
    "get_notifications_enabled",
    "set_notifications_enabled",
    "create_oauth_state",
    "pop_oauth_state",
    "upsert_account",
    "get_accounts",
    "get_account_by_id",
    "get_all_accounts",
    "update_credentials",
    "update_history_id",
    "delete_account",
]

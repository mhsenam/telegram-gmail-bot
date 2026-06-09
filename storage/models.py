"""Shared data types used by both storage backends."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Account:
    id: int
    telegram_id: int
    email: str
    creds_enc: bytes
    last_history_id: str | None

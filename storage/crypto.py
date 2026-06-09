"""Encryption of OAuth tokens at rest.

Gmail refresh tokens are long-lived credentials to a user's mailbox. We never store
them in plaintext: each is encrypted with Fernet (AES-128-CBC + HMAC) using a key that
lives only in the environment (FERNET_KEY), not in the database.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from config import settings

try:
    _fernet = Fernet(settings.fernet_key.encode())
except (ValueError, TypeError) as exc:  # bad/missing key
    raise SystemExit(
        "FERNET_KEY is invalid. Generate one with:\n"
        '  python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"'
    ) from exc


def encrypt(plaintext: str) -> bytes:
    return _fernet.encrypt(plaintext.encode("utf-8"))


def decrypt(token: bytes) -> str:
    try:
        return _fernet.decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        # Happens if FERNET_KEY changed after data was written.
        raise RuntimeError(
            "Could not decrypt a stored token — has FERNET_KEY changed?"
        ) from exc

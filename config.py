"""Central configuration, loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # load variables from a local .env file if present


@dataclass(frozen=True)
class Settings:
    bot_token: str
    google_client_id: str
    google_client_secret: str
    redirect_base_url: str
    web_host: str
    web_port: int
    fernet_key: str
    poll_interval: int
    db_path: str
    database_url: str
    telegram_proxy: str
    connect_timeout: float

    @property
    def redirect_uri(self) -> str:
        """The exact redirect URI that must also be registered in Google Cloud."""
        return self.redirect_base_url.rstrip("/") + "/oauth2callback"


def _load() -> Settings:
    missing: list[str] = []

    def required(key: str) -> str:
        value = os.environ.get(key, "").strip()
        if not value:
            missing.append(key)
        return value

    settings = Settings(
        bot_token=required("TELEGRAM_BOT_TOKEN"),
        google_client_id=required("GOOGLE_CLIENT_ID"),
        google_client_secret=required("GOOGLE_CLIENT_SECRET"),
        redirect_base_url=os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://localhost:8080"),
        web_host=os.environ.get("WEB_HOST", "0.0.0.0"),
        # Honor a platform-provided $PORT (Replit/Render/Heroku) before WEB_PORT.
        web_port=int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8080"),
        fernet_key=required("FERNET_KEY"),
        poll_interval=int(os.environ.get("POLL_INTERVAL_SECONDS", "30")),
        db_path=os.environ.get("DATABASE_PATH", "gmail_bot.db"),
        # If set, use PostgreSQL (persists across redeploys); else fall back to SQLite.
        database_url=os.environ.get("DATABASE_URL", "").strip(),
        telegram_proxy=os.environ.get("TELEGRAM_PROXY", "").strip(),
        connect_timeout=float(os.environ.get("TELEGRAM_CONNECT_TIMEOUT", "20")),
    )
    if missing:
        raise SystemExit(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill it in (see SETUP.md)."
        )
    return settings


settings = _load()

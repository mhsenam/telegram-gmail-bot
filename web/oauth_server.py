"""Tiny aiohttp web server that receives Google's OAuth redirect.

Flow:
  1. User taps "Connect Gmail" -> Google consent screen.
  2. Google redirects the browser to  <BASE>/oauth2callback?code=...&state=...
  3. This server validates `state`, exchanges `code` for tokens, stores them
     (encrypted), and DMs the user via the bot to confirm.
  4. The browser shows a friendly "you can close this tab" page.

It runs on the same event loop as the bot.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from telegram import Bot

from config import settings
from gmailsvc import client as gmail
from gmailsvc import oauth
from storage import crypto, db

log = logging.getLogger(__name__)


def _html(title: str, body: str, ok: bool = True) -> web.Response:
    color = "#16a34a" if ok else "#dc2626"
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
 body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#0f172a;color:#e2e8f0;
   display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 .card{{background:#1e293b;padding:2.5rem;border-radius:16px;max-width:420px;text-align:center;
   box-shadow:0 10px 40px rgba(0,0,0,.4)}}
 h1{{color:{color};margin:0 0 .5rem}} p{{line-height:1.5;color:#94a3b8}}
</style></head>
<body><div class="card"><h1>{title}</h1><p>{body}</p></div></body></html>"""
    return web.Response(text=page, content_type="text/html")


async def _handle_callback(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]

    # User declined consent, or Google returned an error.
    if "error" in request.query:
        return _html("Connection cancelled",
                     "You can close this tab and return to Telegram.", ok=False)

    code = request.query.get("code")
    state = request.query.get("state")
    if not code or not state:
        return _html("Invalid request", "Missing code or state.", ok=False)

    popped = await db.pop_oauth_state(state)
    if popped is None:
        # Unknown/expired/replayed state -> reject (CSRF protection).
        return _html("Link expired",
                     "This connection link is no longer valid. Send /connect again.",
                     ok=False)
    telegram_id, code_verifier = popped

    try:
        creds = await asyncio.to_thread(oauth.exchange_code, code, code_verifier)
        profile = await asyncio.to_thread(gmail.get_profile, creds)
    except Exception:  # noqa: BLE001 — surface a friendly page, log the detail
        log.exception("OAuth exchange failed for telegram_id=%s", telegram_id)
        return _html("Something went wrong",
                     "We couldn't complete the connection. Please try /connect again.",
                     ok=False)

    email = profile.get("emailAddress", "your account")
    history_id = profile.get("historyId")

    # Store the encrypted credentials + baseline history cursor (so we only notify
    # about mail arriving AFTER this moment, never the existing backlog).
    creds_enc = crypto.encrypt(oauth.credentials_to_json(creds))
    await db.ensure_user(telegram_id)
    await db.upsert_account(telegram_id, email, creds_enc, history_id)

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=(f"✅ Connected <b>{email}</b>!\n\n"
                  "I'll notify you here the moment new mail arrives. "
                  "Use /inbox to peek now, or /accounts to manage connections."),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        log.exception("Failed to notify user %s after connect", telegram_id)

    return _html("Gmail connected 🎉",
                 f"{email} is now linked. You can close this tab and return to Telegram.")


async def _health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


def build_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/oauth2callback", _handle_callback)
    app.router.add_get("/", _health)
    return app


async def start_web_server(bot: Bot) -> web.AppRunner:
    app = build_app(bot)
    # Browsers send ALL cookies saved for "localhost" (regardless of port) to our
    # callback, including large ones set by other local dev apps (e.g. Clerk JWTs).
    # aiohttp's default header limit is 8190 bytes, which such cookies can exceed and
    # cause "LineTooLong: 400" before our handler runs. We ignore cookies anyway, so
    # we simply allow larger headers.
    runner = web.AppRunner(app, max_field_size=65536, max_line_size=65536)
    await runner.setup()
    site = web.TCPSite(runner, settings.web_host, settings.web_port)
    await site.start()
    log.info("OAuth callback server listening on %s:%s (redirect_uri=%s)",
             settings.web_host, settings.web_port, settings.redirect_uri)
    return runner

"""Background job: poll every connected inbox and push new mail to its owner.

This gives near-real-time delivery (default every 30s, configurable). It is the simplest
approach that works on ANY host. For TRUE push real-time, see docs/architecture.md
(Gmail watch() + Google Cloud Pub/Sub) — the data model here already supports it.
"""
from __future__ import annotations

import asyncio
import html
import logging
import time

from google.auth.exceptions import RefreshError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from gmailsvc import client as gmail
from gmailsvc import oauth
from storage import crypto, db
from storage.db import Account

log = logging.getLogger(__name__)

# Don't flood a chat if a huge batch arrives at once.
MAX_NOTIFY_PER_POLL = 8

# Wall-clock time of the last completed poll sweep (for /status). In-memory only.
_last_poll_at: float = 0.0


def last_poll_age_seconds() -> int | None:
    """Seconds since the last completed poll sweep, or None if it hasn't run yet."""
    if not _last_poll_at:
        return None
    return max(0, int(time.time() - _last_poll_at))


def _format_email(email: str, m: gmail.MessageMeta) -> str:
    sender = html.escape(m.sender)
    subject = html.escape(m.subject) or "(no subject)"
    snippet = html.escape(m.snippet[:200])
    return (
        f"📧 <b>New email</b> · <code>{html.escape(email)}</code>\n"
        f"👤 {sender}\n"
        f"📝 <b>{subject}</b>\n"
        f"{snippet}"
    )


def _open_gmail_markup(email: str) -> InlineKeyboardMarkup:
    url = f"https://mail.google.com/mail/?authuser={email}#inbox"
    return InlineKeyboardMarkup([[InlineKeyboardButton("📬 Open Gmail", url=url)]])


async def _process_account(context: ContextTypes.DEFAULT_TYPE, acc: Account) -> None:
    if not acc.last_history_id:
        return  # never baselined; skip until a profile fetch sets it

    creds = oauth.credentials_from_json(crypto.decrypt(acc.creds_enc))

    # Refresh access token if needed; persist if it changed.
    try:
        refreshed = await asyncio.to_thread(gmail.ensure_fresh, creds)
    except RefreshError:
        await _handle_revoked(context, acc)
        return
    if refreshed:
        await db.update_credentials(acc.id, crypto.encrypt(oauth.credentials_to_json(creds)))

    try:
        ids, latest, expired = await asyncio.to_thread(
            gmail.list_new_inbox_message_ids, creds, acc.last_history_id
        )
    except RefreshError:
        await _handle_revoked(context, acc)
        return
    except Exception:  # noqa: BLE001
        log.exception("history.list failed for account %s", acc.id)
        return

    if expired:
        # Cursor too old; re-baseline from current profile (no notifications this round).
        try:
            profile = await asyncio.to_thread(gmail.get_profile, creds)
            await db.update_history_id(acc.id, profile["historyId"])
        except Exception:  # noqa: BLE001
            log.exception("re-baseline failed for account %s", acc.id)
        return

    if not ids:
        if latest:
            await db.update_history_id(acc.id, latest)
        return

    # Respect the user's notification preference (but still advance the cursor).
    if await db.get_notifications_enabled(acc.telegram_id):
        for message_id in ids[:MAX_NOTIFY_PER_POLL]:
            try:
                meta = await asyncio.to_thread(gmail.get_message_meta, creds, message_id)
            except Exception:  # noqa: BLE001
                log.exception("get message %s failed", message_id)
                continue
            try:
                await context.bot.send_message(
                    chat_id=acc.telegram_id,
                    text=_format_email(acc.email, meta),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_open_gmail_markup(acc.email),
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except Exception:  # noqa: BLE001
                # e.g. user blocked the bot — don't let one failure stop the batch.
                log.warning("could not deliver to %s", acc.telegram_id)
        overflow = len(ids) - MAX_NOTIFY_PER_POLL
        if overflow > 0:
            await context.bot.send_message(
                chat_id=acc.telegram_id,
                text=f"…and {overflow} more new message(s) in {html.escape(acc.email)}.",
            )

    if latest:
        await db.update_history_id(acc.id, latest)


async def _handle_revoked(context: ContextTypes.DEFAULT_TYPE, acc: Account) -> None:
    """The user revoked our access in their Google settings -> clean up + inform."""
    log.info("access revoked for account %s (%s); removing", acc.id, acc.email)
    await db.delete_account(acc.id)
    try:
        await context.bot.send_message(
            chat_id=acc.telegram_id,
            text=(f"⚠️ Access to <code>{html.escape(acc.email)}</code> was revoked, so I "
                  "disconnected it. Use /connect to link it again."),
            parse_mode=ParseMode.HTML,
        )
    except Exception:  # noqa: BLE001
        pass


async def poll_all(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue entry point — runs on the configured interval."""
    global _last_poll_at
    accounts = await db.get_all_accounts()
    for acc in accounts:
        try:
            await _process_account(context, acc)
        except Exception:  # noqa: BLE001 — never let one account kill the whole sweep
            log.exception("unexpected error processing account %s", acc.id)
    _last_poll_at = time.time()

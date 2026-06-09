"""Command + callback handlers (the bot's user-facing surface)."""
from __future__ import annotations

import asyncio
import html
import logging
import secrets

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot import keyboards, notifier
from bot.progress import Progress
from config import settings
from gmailsvc import client as gmail
from gmailsvc import oauth
from storage import crypto, db

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Basic / info commands
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db.ensure_user(user.id)
    await update.message.reply_text(
        f"👋 Hi <b>{html.escape(user.first_name)}</b>! I'm your personal inbox assistant.\n\n"
        "I notify you in real-time whenever new mail arrives in a Gmail account you "
        "connect — and more services are coming.\n\n"
        "▶️ <b>/connect</b> — link a Gmail account\n"
        "📥 <b>/inbox</b> — show your latest emails now\n"
        "📂 <b>/accounts</b> — manage connected accounts\n"
        "📊 <b>/status</b> — connection &amp; sync status\n"
        "⚙️ <b>/settings</b> — notifications on/off\n"
        "🔒 <b>/privacy</b> — what data I access\n"
        "ℹ️ <b>/about</b> — about this bot\n"
        "❓ <b>/help</b> — this menu\n\n"
        "Your Gmail is accessed <b>read-only</b>, tokens are stored <b>encrypted</b>, and "
        "you can disconnect anytime.",
        parse_mode=ParseMode.HTML,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🤖 <b>Gmail Super Bot</b>\n"
        "A multi-service Telegram assistant. First service: real-time Gmail inbox. "
        "Privacy-first — read-only Gmail access, encrypted tokens, one-tap disconnect.\n\n"
        "👨‍💻 <b>Built by Mohsen Amini</b>\n"
        "Frontend engineer with ~4 years building production <b>React</b> &amp; "
        "<b>Next.js</b> apps in <b>TypeScript</b> for remote, international teams. "
        "The last two years focused on <b>AI / LLM-powered interfaces</b> — streaming chat "
        "UIs, multi-provider agent orchestration, and real-time monitoring dashboards — with "
        "the OpenAI, Anthropic Claude, and Gemini APIs. Big on <b>performance</b> and "
        "<b>accessibility</b>, and comfortable owning a feature end to end, from "
        "design-system primitives through to edge-rendered production.\n\n"
        '📬 Contact: <a href="https://t.me/mhsenam">@mhsenam</a>',
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔒 <b>Privacy</b>\n\n"
        "• I request <b>read-only</b> Gmail access (scope <code>gmail.readonly</code>) and "
        "your email address — nothing else.\n"
        "• I <b>cannot</b> send, delete, or modify your email.\n"
        "• Your access tokens are <b>encrypted at rest</b>; I never store your password.\n"
        "• I only read message <i>headers</i> and short previews to notify you.\n"
        "• <b>/disconnect</b> revokes my access and deletes your tokens immediately.\n"
        "• You can also revoke access anytime at "
        "https://myaccount.google.com/permissions",
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ---------------------------------------------------------------------------
# Connect flow
# ---------------------------------------------------------------------------
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db.ensure_user(user.id)

    # CSRF-protected state token tying this OAuth attempt to this Telegram user.
    state = secrets.token_urlsafe(32)
    auth_url, code_verifier = oauth.build_auth_url(state)
    await db.create_oauth_state(state, user.id, code_verifier)

    await update.effective_message.reply_text(
        "🔗 <b>Connect a Gmail account</b>\n\n"
        "Tap the button below, sign in to the Google account you want, and approve "
        "<b>read-only</b> access. You'll be sent straight back here.\n\n"
        "You can connect multiple accounts — just run /connect again.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.connect_button(auth_url),
    )


# ---------------------------------------------------------------------------
# Accounts management
# ---------------------------------------------------------------------------
async def accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    accts = await db.get_accounts(user.id)
    message = update.effective_message
    if not accts:
        await message.reply_text(
            "You have no connected accounts yet. Use /connect to add one."
        )
        return
    lines = "\n".join(f"• <code>{html.escape(a.email)}</code>" for a in accts)
    await message.reply_text(
        f"📂 <b>Connected accounts</b>\n{lines}\n\nManage them below:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.accounts_keyboard(accts),
    )


async def disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /disconnect just shows the accounts list with disconnect buttons.
    await accounts(update, context)


# ---------------------------------------------------------------------------
# Inbox (on demand)
# ---------------------------------------------------------------------------
async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    accts = await db.get_accounts(user.id)
    message = update.effective_message
    if not accts:
        await message.reply_text("No accounts connected. Use /connect first.")
        return

    # Fetch everything behind an animated "loading… <timer>" message, then render results.
    results: list[tuple[str, list[gmail.MessageMeta] | None]] = []
    async with Progress(context.bot, message.chat_id, "Loading your inbox") as prog:
        for acc in accts:
            if len(accts) > 1:
                await prog.set_label(f"Reading {acc.email}")
            try:
                creds = oauth.credentials_from_json(crypto.decrypt(acc.creds_enc))
                refreshed = await asyncio.to_thread(gmail.ensure_fresh, creds)
                if refreshed:
                    await db.update_credentials(
                        acc.id, crypto.encrypt(oauth.credentials_to_json(creds))
                    )
                recent = await asyncio.to_thread(gmail.list_recent_inbox, creds, 5)
                results.append((acc.email, recent))
            except Exception:  # noqa: BLE001
                log.exception("inbox fetch failed for %s", acc.email)
                results.append((acc.email, None))  # None == error

    # Loading message is gone now; send the actual results.
    for email, recent in results:
        if recent is None:
            await message.reply_text(
                f"⚠️ Couldn't read <code>{html.escape(email)}</code>. "
                "Try /accounts to reconnect.",
                parse_mode=ParseMode.HTML,
            )
            continue
        if not recent:
            await message.reply_text(
                f"📭 <code>{html.escape(email)}</code> inbox looks empty.",
                parse_mode=ParseMode.HTML,
            )
            continue

        body = [f"📥 <b>Latest in</b> <code>{html.escape(email)}</code>:"]
        for m in recent:
            subj = html.escape(m.subject) or "(no subject)"
            sender = html.escape(m.sender)
            body.append(f"\n👤 {sender}\n📝 <b>{subj}</b>\n{html.escape(m.snippet[:120])}")
        await message.reply_text(
            "\n".join(body),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db.ensure_user(user.id)
    enabled = await db.get_notifications_enabled(user.id)
    state = "ON 🔔" if enabled else "OFF 🔕"
    await update.effective_message.reply_text(
        f"⚙️ <b>Settings</b>\n\nReal-time notifications: <b>{state}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.settings_keyboard(enabled),
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await db.ensure_user(user.id)
    accts = await db.get_accounts(user.id)
    enabled = await db.get_notifications_enabled(user.id)
    backend = "PostgreSQL" if settings.database_url else "SQLite"

    age = notifier.last_poll_age_seconds()
    last_check = f"{age}s ago" if age is not None else "starting up…"

    lines = [
        "📊 <b>Status</b>",
        "",
        f"🔔 Notifications: <b>{'ON' if enabled else 'OFF'}</b>",
        f"⏱ Checking for new mail every <b>{settings.poll_interval}s</b>",
        f"🕑 Last check: <b>{last_check}</b>",
        f"🗄 Storage: <b>{backend}</b>",
        "",
    ]
    if not accts:
        lines.append("📂 No accounts connected yet. Use /connect to add one.")
    else:
        lines.append(f"📂 <b>Connected accounts ({len(accts)}):</b>")
        for a in accts:
            state = "✅ syncing" if a.last_history_id else "⏳ initializing"
            lines.append(f"• <code>{html.escape(a.email)}</code> — {state}")

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ---------------------------------------------------------------------------
# Callback query router (inline button taps)
# ---------------------------------------------------------------------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    user_id = query.from_user.id

    if data == "connect":
        await query.answer()
        await connect(update, context)
        return

    if data == "accounts":
        await query.answer()
        accts = await db.get_accounts(user_id)
        if not accts:
            await query.edit_message_text("No connected accounts. Use /connect.")
        else:
            lines = "\n".join(f"• <code>{html.escape(a.email)}</code>" for a in accts)
            await query.edit_message_text(
                f"📂 <b>Connected accounts</b>\n{lines}\n\nManage them below:",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboards.accounts_keyboard(accts),
            )
        return

    if data.startswith("disconnect:"):
        account_id = int(data.split(":", 1)[1])
        acc = await db.get_account_by_id(account_id)
        if not acc or acc.telegram_id != user_id:  # ownership check
            await query.answer("Not found.", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            f"Disconnect <code>{html.escape(acc.email)}</code>? "
            "This revokes my access and deletes your tokens.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.confirm_disconnect_keyboard(acc.id, acc.email),
        )
        return

    if data.startswith("disconnect_yes:"):
        account_id = int(data.split(":", 1)[1])
        acc = await db.get_account_by_id(account_id)
        if not acc or acc.telegram_id != user_id:  # ownership check
            await query.answer("Not found.", show_alert=True)
            return
        await query.answer("Disconnecting…")
        try:
            creds = oauth.credentials_from_json(crypto.decrypt(acc.creds_enc))
            await asyncio.to_thread(oauth.revoke, creds)
        except Exception:  # noqa: BLE001
            log.exception("revoke failed for %s", acc.email)
        await db.delete_account(acc.id)
        await query.edit_message_text(
            f"✅ Disconnected <code>{html.escape(acc.email)}</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "toggle_notif":
        enabled = await db.get_notifications_enabled(user_id)
        await db.set_notifications_enabled(user_id, not enabled)
        new_state = "ON 🔔" if not enabled else "OFF 🔕"
        await query.answer(f"Notifications {new_state}")
        await query.edit_message_text(
            f"⚙️ <b>Settings</b>\n\nReal-time notifications: <b>{new_state}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.settings_keyboard(not enabled),
        )
        return

    await query.answer()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Handler error", exc_info=context.error)

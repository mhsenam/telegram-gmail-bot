"""Inline keyboards used across the bot."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from storage.db import Account


def connect_button(auth_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔗 Connect Gmail", url=auth_url)]]
    )


def accounts_keyboard(accounts: list[Account]) -> InlineKeyboardMarkup:
    """One 'disconnect' button per connected account, plus an 'add another' button."""
    rows = [
        [InlineKeyboardButton(f"🗑 Disconnect {acc.email}", callback_data=f"disconnect:{acc.id}")]
        for acc in accounts
    ]
    rows.append([InlineKeyboardButton("➕ Connect another account", callback_data="connect")])
    return InlineKeyboardMarkup(rows)


def confirm_disconnect_keyboard(account_id: int, email: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"✅ Yes, disconnect {email}",
                                  callback_data=f"disconnect_yes:{account_id}")],
            [InlineKeyboardButton("↩️ Cancel", callback_data="accounts")],
        ]
    )


def settings_keyboard(notifications_enabled: bool) -> InlineKeyboardMarkup:
    label = "🔕 Turn notifications OFF" if notifications_enabled else "🔔 Turn notifications ON"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data="toggle_notif")]]
    )

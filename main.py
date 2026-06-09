"""Entry point: runs the Telegram bot (long polling), the background mail poller,
and the OAuth callback web server — all on one asyncio event loop.

    python main.py
"""
from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand, MenuButtonCommands, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
)

from bot import handlers
from bot.notifier import poll_all
from config import settings
from storage import db
from web.oauth_server import start_web_server

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
# Quiet noisy libraries.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
log = logging.getLogger("main")

COMMANDS = [
    BotCommand("start", "Start / show the menu"),
    BotCommand("connect", "Connect a Gmail account"),
    BotCommand("inbox", "Show your latest emails"),
    BotCommand("accounts", "Manage connected accounts"),
    BotCommand("status", "Connection & sync status"),
    BotCommand("settings", "Notifications on/off"),
    BotCommand("privacy", "What data I access"),
    BotCommand("about", "About this bot"),
    BotCommand("help", "Help"),
]


def build_application():
    builder = (
        ApplicationBuilder()
        .token(settings.bot_token)
        # Tolerate slow/restricted routes to api.telegram.org.
        .connect_timeout(settings.connect_timeout)
        .read_timeout(settings.connect_timeout)
    )
    # Optional proxy for reaching Telegram (e.g. where api.telegram.org is blocked).
    # Supports http://host:port  or  socks5://host:port  (socks needs httpx[socks]).
    if settings.telegram_proxy:
        builder = builder.proxy(settings.telegram_proxy).get_updates_proxy(
            settings.telegram_proxy
        )
        log.info("Using proxy for Telegram: %s", settings.telegram_proxy)
    app = builder.build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("about", handlers.about))
    app.add_handler(CommandHandler("privacy", handlers.privacy))
    app.add_handler(CommandHandler("connect", handlers.connect))
    app.add_handler(CommandHandler("accounts", handlers.accounts))
    app.add_handler(CommandHandler("disconnect", handlers.disconnect))
    app.add_handler(CommandHandler("inbox", handlers.inbox))
    app.add_handler(CommandHandler("status", handlers.status_cmd))
    app.add_handler(CommandHandler("settings", handlers.settings_cmd))
    app.add_handler(CallbackQueryHandler(handlers.on_callback))
    app.add_error_handler(handlers.on_error)

    # Background poller — near-real-time inbox checks.
    app.job_queue.run_repeating(poll_all, interval=settings.poll_interval, first=10)
    return app


async def main() -> None:
    await db.init_db()
    app = build_application()

    async with app:  # initializes the bot + job queue
        await app.bot.set_my_commands(COMMANDS)
        # Show the "commands" menu button (the grid/four-square icon next to the input box):
        # tapping it lists every command as a tappable button, alongside the / slash menu.
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        # Start the OAuth callback server only after the bot is initialized, so it can
        # safely send confirmation messages.
        runner = await start_web_server(app.bot)
        log.info("Bot is running. Press Ctrl+C to stop.")
        try:
            await asyncio.Event().wait()  # run forever
        finally:
            await runner.cleanup()
            await app.updater.stop()
            await app.stop()
            log.info("Shut down cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

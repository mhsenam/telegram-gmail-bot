"""A reusable animated "loading…" message with a live timer.

Usage:
    async with Progress(context.bot, chat_id, "Loading your inbox") as prog:
        await prog.set_label("Reading you@gmail.com")   # optional, update the text
        ... do slow work ...
    # the loading message is removed automatically on exit; send your real content after.

It posts one message and edits it ~once per second to tick the timer and animate a spinner,
so the user always sees that something is happening instead of dead air.
"""
from __future__ import annotations

import asyncio
import time

from telegram import Bot, Message
from telegram.constants import ParseMode

_FRAMES = ["⏳", "⌛"]


class Progress:
    def __init__(self, bot: Bot, chat_id: int, label: str = "Working", interval: float = 1.0):
        self._bot = bot
        self._chat_id = chat_id
        self._label = label
        self._interval = interval
        self._message: Message | None = None
        self._task: asyncio.Task | None = None
        self._start = 0.0
        self._frame = 0

    def _render(self) -> str:
        elapsed = int(time.monotonic() - self._start)
        spinner = _FRAMES[self._frame % len(_FRAMES)]
        return f"{spinner} <b>{self._label}…</b>  <code>{elapsed}s</code>"

    async def _safe_edit(self) -> None:
        if not self._message:
            return
        try:
            await self._message.edit_text(self._render(), parse_mode=ParseMode.HTML)
        except Exception:  # noqa: BLE001 — ignore "not modified"/transient edit errors
            pass

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                self._frame += 1
                await self._safe_edit()
        except asyncio.CancelledError:
            pass

    async def set_label(self, label: str) -> None:
        self._label = label
        await self._safe_edit()

    async def __aenter__(self) -> "Progress":
        self._start = time.monotonic()
        self._message = await self._bot.send_message(
            self._chat_id, self._render(), parse_mode=ParseMode.HTML
        )
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._message:
            try:
                await self._message.delete()
            except Exception:  # noqa: BLE001
                pass

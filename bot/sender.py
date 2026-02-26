import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


async def send_long_message(update: Update, text: str):
    """Send a message, splitting into chunks if needed."""
    if not text:
        text = "(빈 응답)"
    chunks = split_message(text)
    for chunk in chunks:
        await update.message.reply_text(chunk)


def split_message(text: str) -> list[str]:
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            chunks.append(text)
            break
        # Try to split at newline
        split_pos = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_pos == -1:
            split_pos = MAX_MESSAGE_LENGTH
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


class ProgressIndicator:
    """Sends and updates a '⏳ 처리 중...' message periodically."""

    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._update = update
        self._context = context
        self._message = None
        self._task: asyncio.Task | None = None
        self._elapsed = 0

    async def start(self):
        self._message = await self._update.message.reply_text("⏳ 처리 중...")
        self._task = asyncio.create_task(self._updater())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._message:
            try:
                await self._message.delete()
            except Exception:
                pass

    async def _updater(self):
        try:
            while True:
                await asyncio.sleep(10)
                self._elapsed += 10
                try:
                    await self._message.edit_text(
                        f"⏳ 처리 중... ({self._elapsed}초 경과)"
                    )
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

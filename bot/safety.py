import json
import os
import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

# Pending confirmations: callback_data_id -> asyncio.Future
_pending: dict[str, asyncio.Future] = {}
_counter = 0


def _load_safety_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("safety", {})
    return {}


def needs_confirmation(message: str) -> bool:
    config = _load_safety_config()
    keywords = config.get("confirm_keywords", [])
    lower = message.lower()
    return any(kw.lower() in lower for kw in keywords)


async def request_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> bool:
    global _counter
    _counter += 1
    confirm_id = f"safety_{_counter}"

    config = _load_safety_config()
    confirm_msg = config.get("confirm_message", "⚠️ 위험할 수 있는 작업입니다. 실행할까요?")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 실행", callback_data=f"{confirm_id}_yes"),
            InlineKeyboardButton("❌ 취소", callback_data=f"{confirm_id}_no"),
        ]
    ])

    await update.message.reply_text(
        f"{confirm_msg}\n\n`{message[:200]}`",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    future = asyncio.get_event_loop().create_future()
    _pending[confirm_id] = future

    try:
        result = await asyncio.wait_for(future, timeout=120)
        return result
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ 승인 시간 초과. 작업이 취소되었습니다.")
        return False
    finally:
        _pending.pop(confirm_id, None)


async def handle_safety_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # Parse: safety_N_yes or safety_N_no
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        return

    confirm_id = parts[0]
    choice = parts[1]
    future = _pending.get(confirm_id)

    if future and not future.done():
        approved = choice == "yes"
        future.set_result(approved)
        status = "✅ 실행 승인됨" if approved else "❌ 취소됨"
        await query.edit_message_text(status)
    else:
        await query.edit_message_text("(이미 처리됨)")

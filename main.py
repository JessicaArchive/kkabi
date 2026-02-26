import asyncio
import json
import logging
import os
import signal
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.handlers import (
    handle_message,
    handle_file,
    cmd_cd,
    cmd_pwd,
    cmd_status,
    cmd_history,
    cmd_memory,
    cmd_memory_add,
    cmd_memory_clear,
    cmd_forget,
    cmd_system,
    cmd_getfile,
    cmd_cancel,
    cmd_running,
    cmd_help,
    cmd_cron,
)
from bot.safety import handle_safety_callback
from claude.queue import execution_queue
from db.store import init_db
from memory.manager import cleanup_old_logs
from scheduler.cron import init_scheduler, shutdown_scheduler

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "logs", "kkabi.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("kkabi")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        logger.error("config.json이 없습니다. config.example.json을 복사해서 만드세요.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    config = load_config()
    token = config["telegram"]["bot_token"]
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error("config.json에 유효한 bot_token을 설정하세요.")
        sys.exit(1)

    # Ensure runtime dirs
    os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "data", "uploads"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "data", "memory", "logs"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "data", "memory", "projects"), exist_ok=True)

    # Build application
    app = Application.builder().token(token).build()

    # Command handlers
    app.add_handler(CommandHandler("cd", cmd_cd))
    app.add_handler(CommandHandler("pwd", cmd_pwd))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("memory_add", cmd_memory_add))
    app.add_handler(CommandHandler("memory_clear", cmd_memory_clear))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("system", cmd_system))
    app.add_handler(CommandHandler("getfile", cmd_getfile))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("running", cmd_running))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("cron", cmd_cron))

    # Callback query (safety confirmation)
    app.add_handler(CallbackQueryHandler(handle_safety_callback))

    # File handler (documents + photos)
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    # General message handler (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Post-init: start scheduler, DB, queue
    async def post_init(application: Application):
        await init_db()
        execution_queue.start()

        # Telegram send function for cron results
        allowed = config.get("telegram", {}).get("allowed_user_ids", [])
        chat_id = allowed[0] if allowed else None

        async def send_to_telegram(text: str):
            if chat_id:
                from bot.sender import split_message
                for chunk in split_message(text):
                    await application.bot.send_message(chat_id=chat_id, text=chunk)

        init_scheduler(send_func=send_to_telegram if chat_id else None)

        # Cleanup old logs
        retention = config.get("memory", {}).get("log_retention_days", 30)
        removed = cleanup_old_logs(retention)
        if removed:
            logger.info("오래된 로그 %d개 삭제", removed)

        logger.info("Kkabi 시작됨!")

    async def post_shutdown(application: Application):
        shutdown_scheduler()
        await execution_queue.stop()
        logger.info("Kkabi 종료됨")

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    # Run (polling mode — no inbound ports needed)
    logger.info("텔레그램 봇 시작 중...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

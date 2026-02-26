import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Download a file sent by user, return local path."""
    _ensure_upload_dir()

    doc = update.message.document
    photo = update.message.photo

    if doc:
        if doc.file_size and doc.file_size > MAX_UPLOAD_BYTES:
            await update.message.reply_text(f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB)")
            return None
        tg_file = await doc.get_file()
        filename = doc.file_name or f"upload_{doc.file_id}"
    elif photo:
        # Use the largest photo
        largest = photo[-1]
        tg_file = await largest.get_file()
        filename = f"photo_{largest.file_id}.jpg"
    else:
        return None

    local_path = os.path.join(UPLOAD_DIR, filename)

    # Avoid overwriting
    base, ext = os.path.splitext(local_path)
    counter = 1
    while os.path.exists(local_path):
        local_path = f"{base}_{counter}{ext}"
        counter += 1

    await tg_file.download_to_drive(local_path)
    logger.info("파일 저장: %s", local_path)
    return local_path


async def send_file(update: Update, file_path: str):
    """Send a file from server to telegram."""
    expanded = os.path.expanduser(file_path)
    if not os.path.exists(expanded):
        await update.message.reply_text(f"파일을 찾을 수 없습니다: {file_path}")
        return

    file_size = os.path.getsize(expanded)
    if file_size > MAX_UPLOAD_BYTES:
        await update.message.reply_text(f"파일이 너무 큽니다 ({file_size // 1024 // 1024}MB, 최대 50MB)")
        return

    await update.message.reply_document(document=open(expanded, "rb"), filename=os.path.basename(expanded))

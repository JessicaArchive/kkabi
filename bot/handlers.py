import json
import os
import functools
import logging
from telegram import Update
from telegram.ext import ContextTypes

from claude.runner import run_claude, cancel_task, is_running
from claude.context import build_full_prompt, load_system_prompt, save_system_prompt
from claude.queue import execution_queue
from claude.retry import retry_queue
from db.store import save_execution, save_conversation, get_recent_executions, get_recent_conversations
from memory.manager import load_memory, append_to_memory, clear_today_log, get_memory_summary
from bot.sender import send_long_message, ProgressIndicator
from bot.file_transfer import handle_file_upload, send_file
from bot.safety import needs_confirmation, request_confirmation

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

# Per-user working directory
_work_dirs: dict[int, str] = {}


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _get_work_dir(user_id: int) -> str:
    config = _load_config()
    default = os.path.expanduser(config.get("claude", {}).get("default_work_dir", "~"))
    return _work_dirs.get(user_id, default)


def _get_timeout() -> int:
    config = _load_config()
    return config.get("claude", {}).get("timeout_sec", 300)


def _get_max_turns() -> int:
    config = _load_config()
    return config.get("memory", {}).get("max_context_turns", 5)


def _get_response_limit() -> int:
    config = _load_config()
    return config.get("memory", {}).get("response_save_limit", 500)


def authorized(func):
    """Decorator to check if user is in allowed_user_ids."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        config = _load_config()
        allowed = config.get("telegram", {}).get("allowed_user_ids", [])
        user_id = update.effective_user.id
        if allowed and user_id not in allowed:
            logger.warning("Unauthorized access from user %d", user_id)
            await update.message.reply_text("⛔ 권한이 없습니다.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# ─── General message handler ───

@authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    work_dir = _get_work_dir(user_id)

    # Safety check
    if needs_confirmation(user_message):
        approved = await request_confirmation(update, context, user_message)
        if not approved:
            return

    # Queue check
    pending = execution_queue.pending_count
    if pending > 0:
        await update.message.reply_text(f"📋 대기 중 (앞에 {pending}개 작업)")

    async def _execute():
        prompt = await build_full_prompt(user_message, max_turns=_get_max_turns())
        return await run_claude(prompt, work_dir, timeout_sec=_get_timeout(), chat_id=chat_id)

    progress = ProgressIndicator(update, context)
    await progress.start()

    try:
        future = await execution_queue.submit(_execute)
        result = await future
    finally:
        await progress.stop()

    # Save records
    response_text = result.get("result") or result.get("error") or "(응답 없음)"
    trimmed_response = response_text[:_get_response_limit()]
    await save_conversation(user_message, trimmed_response, work_dir, result["duration"])
    await save_execution(
        source="telegram",
        prompt=user_message,
        result=response_text,
        duration_sec=result["duration"],
        work_dir=work_dir,
        status=result["status"],
        error_message=result.get("error"),
    )

    # Log to memory
    from memory.manager import log_conversation
    log_conversation(user_message, response_text)

    # Handle rate limit retry
    if result["status"] == "rate_limited":
        await update.message.reply_text("⚠️ API 한도 초과. 5분 후 자동 재시도합니다.")

        async def retry_callback(retry_result, error):
            if error:
                await update.message.reply_text(f"❌ 재시도 실패: {error}")
            elif retry_result:
                text = retry_result.get("result") or retry_result.get("error") or "(응답 없음)"
                await send_long_message(update, f"🔄 재시도 결과:\n{text}")

        async def retry_run(p, w):
            return await run_claude(p, w, timeout_sec=_get_timeout(), chat_id=chat_id)

        prompt = await build_full_prompt(user_message, max_turns=_get_max_turns())
        asyncio.create_task(retry_queue.schedule_retry(retry_run, prompt, work_dir, retry_callback))
        return

    await send_long_message(update, response_text)


# ─── File handler ───

@authorized
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    local_path = await handle_file_upload(update, context)
    if not local_path:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    work_dir = _get_work_dir(user_id)
    caption = update.message.caption or "이 파일을 확인해주세요"
    user_message = f"사용자가 파일을 보냈습니다: {local_path}\n{caption}"

    prompt = await build_full_prompt(user_message, max_turns=_get_max_turns())
    progress = ProgressIndicator(update, context)
    await progress.start()
    try:
        future = await execution_queue.submit(
            run_claude, prompt, work_dir, _get_timeout(), chat_id
        )
        result = await future
    finally:
        await progress.stop()

    response_text = result.get("result") or result.get("error") or "(응답 없음)"
    trimmed = response_text[:_get_response_limit()]
    await save_conversation(user_message, trimmed, work_dir, result["duration"])
    await save_execution("telegram", user_message, response_text, result["duration"], work_dir, result["status"], result.get("error"))
    from memory.manager import log_conversation
    log_conversation(caption, response_text)
    await send_long_message(update, response_text)


# ─── Command handlers ───

@authorized
async def cmd_cd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /cd <경로>")
        return
    path = os.path.expanduser(" ".join(context.args))
    if not os.path.isdir(path):
        await update.message.reply_text(f"디렉토리가 존재하지 않습니다: {path}")
        return
    _work_dirs[update.effective_user.id] = path
    await update.message.reply_text(f"📂 작업 디렉토리 변경: {path}")


@authorized
async def cmd_pwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    work_dir = _get_work_dir(update.effective_user.id)
    await update.message.reply_text(f"📂 현재 작업 디렉토리: {work_dir}")


@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import shutil
    import subprocess
    import platform

    lines = ["📊 시스템 상태\n"]

    # Uptime
    try:
        result = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
        lines.append(f"⏱ 업타임: {result.stdout.strip()}")
    except Exception:
        lines.append(f"⏱ OS: {platform.system()} {platform.release()}")

    # Claude version
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        lines.append(f"🤖 Claude: {result.stdout.strip()}")
    except Exception:
        lines.append("🤖 Claude: (확인 불가)")

    # Memory
    mem = load_memory()
    lines.append(f"🧠 메모리: {len(mem)}자")

    # Work dir
    work_dir = _get_work_dir(update.effective_user.id)
    lines.append(f"📂 작업 디렉토리: {work_dir}")

    # Queue
    lines.append(f"📋 대기 큐: {execution_queue.pending_count}개")

    await update.message.reply_text("\n".join(lines))


@authorized
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = 10
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            pass
    records = await get_recent_executions(n)
    if not records:
        await update.message.reply_text("실행 기록이 없습니다.")
        return
    lines = [f"📜 최근 {len(records)}개 실행 기록\n"]
    for r in records:
        ts = r["timestamp"][:16]
        status_icon = {"success": "✅", "error": "❌", "timeout": "⏰", "rate_limited": "🔄"}.get(r["status"], "❓")
        prompt_short = r["prompt"][:40]
        dur = f"{r['duration_sec']:.1f}s" if r["duration_sec"] else "?"
        lines.append(f"{status_icon} [{ts}] {prompt_short}... ({dur})")
    await send_long_message(update, "\n".join(lines))


@authorized
async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = get_memory_summary()
    await send_long_message(update, f"🧠 메모리 내용:\n\n{summary}")


@authorized
async def cmd_memory_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /memory_add <내용>")
        return
    text = " ".join(context.args)
    append_to_memory(text)
    await update.message.reply_text(f"✅ 메모리에 추가됨: {text}")


@authorized
async def cmd_memory_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if clear_today_log():
        await update.message.reply_text("🗑 오늘 로그 초기화 완료")
    else:
        await update.message.reply_text("오늘 로그가 없습니다.")


@authorized
async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Clear conversation history by deleting all records
    import aiosqlite
    from db.store import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversations")
        await db.commit()
    await update.message.reply_text("🔄 대화 맥락 초기화 완료")


@authorized
async def cmd_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        current = load_system_prompt()
        await send_long_message(update, f"현재 시스템 프롬프트:\n\n{current}")
        return
    new_prompt = " ".join(context.args)
    save_system_prompt(new_prompt)
    await update.message.reply_text(f"✅ 시스템 프롬프트 변경됨:\n{new_prompt}")


@authorized
async def cmd_getfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("사용법: /getfile <경로>")
        return
    file_path = " ".join(context.args)
    await send_file(update, file_path)


@authorized
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if await cancel_task(chat_id):
        await update.message.reply_text("🛑 현재 작업이 취소되었습니다.")
    else:
        await update.message.reply_text("실행 중인 작업이 없습니다.")


@authorized
async def cmd_running(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if is_running(chat_id):
        await update.message.reply_text("▶️ 현재 Claude 작업이 실행 중입니다.")
    else:
        await update.message.reply_text("실행 중인 작업이 없습니다.")


@authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 *Kkabi 도움말*

*일반 메시지* — Claude에게 전달
*파일 전송* — 파일 업로드 후 Claude가 분석

*명령어:*
/cd <경로> — 작업 디렉토리 변경
/pwd — 현재 작업 디렉토리
/status — 시스템 상태
/history [N] — 최근 실행 기록
/memory — 메모리 내용
/memory\\_add <내용> — 메모리에 추가
/memory\\_clear — 오늘 로그 초기화
/forget — 대화 맥락 초기화
/system [프롬프트] — 시스템 프롬프트 확인/변경
/getfile <경로> — 서버 파일 다운로드
/cron list — 크론잡 목록
/cron add <표현식> <설명> — 크론잡 추가
/cron remove <ID> — 크론잡 삭제
/cron toggle <ID> — 크론잡 활성화/비활성화
/cancel — 현재 작업 취소
/running — 실행 중 작업 확인
/help — 이 도움말"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ─── Cron commands ───

@authorized
async def cmd_cron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from scheduler.cron import list_crons, add_cron, remove_cron, toggle_cron

    if not context.args:
        await update.message.reply_text("사용법: /cron list | add | remove | toggle")
        return

    sub = context.args[0].lower()

    if sub == "list":
        crons = list_crons()
        if not crons:
            await update.message.reply_text("등록된 크론잡이 없습니다.")
            return
        lines = ["⏰ 크론잡 목록\n"]
        for c in crons:
            status = "✅" if c.get("enabled", True) else "⏸"
            lines.append(f"{status} `{c['id']}` — {c.get('name', c['id'])}\n   {c['cron']} | {c['prompt'][:40]}...")
        await send_long_message(update, "\n".join(lines))

    elif sub == "add":
        # /cron add "*/5 * * * *" "설명"
        rest = " ".join(context.args[1:])
        parts = rest.split('"')
        quoted = [p.strip() for p in parts if p.strip()]
        if len(quoted) < 2:
            await update.message.reply_text('사용법: /cron add "표현식" "프롬프트/설명"')
            return
        cron_expr = quoted[0]
        prompt = quoted[1]
        work_dir = _get_work_dir(update.effective_user.id)
        cron_id = add_cron(cron_expr, prompt, work_dir)
        await update.message.reply_text(f"✅ 크론잡 추가됨: `{cron_id}`\n{cron_expr} → {prompt}")

    elif sub == "remove":
        if len(context.args) < 2:
            await update.message.reply_text("사용법: /cron remove <ID>")
            return
        cron_id = context.args[1]
        if remove_cron(cron_id):
            await update.message.reply_text(f"🗑 크론잡 삭제됨: {cron_id}")
        else:
            await update.message.reply_text(f"크론잡을 찾을 수 없습니다: {cron_id}")

    elif sub == "toggle":
        if len(context.args) < 2:
            await update.message.reply_text("사용법: /cron toggle <ID>")
            return
        cron_id = context.args[1]
        new_state = toggle_cron(cron_id)
        if new_state is not None:
            icon = "✅ 활성화" if new_state else "⏸ 비활성화"
            await update.message.reply_text(f"{icon}: {cron_id}")
        else:
            await update.message.reply_text(f"크론잡을 찾을 수 없습니다: {cron_id}")

    else:
        await update.message.reply_text("사용법: /cron list | add | remove | toggle")


import asyncio

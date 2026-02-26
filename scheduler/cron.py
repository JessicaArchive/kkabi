import json
import os
import uuid
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

CRONS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "crons.json")

_scheduler: AsyncIOScheduler | None = None
_send_telegram_func = None  # Will be set by main.py


def _load_crons() -> list[dict]:
    if os.path.exists(CRONS_PATH):
        with open(CRONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_crons(crons: list[dict]):
    os.makedirs(os.path.dirname(CRONS_PATH), exist_ok=True)
    with open(CRONS_PATH, "w", encoding="utf-8") as f:
        json.dump(crons, f, indent=2, ensure_ascii=False)


def list_crons() -> list[dict]:
    return _load_crons()


def add_cron(cron_expr: str, prompt: str, work_dir: str, name: str | None = None) -> str:
    crons = _load_crons()
    cron_id = str(uuid.uuid4())[:8]
    entry = {
        "id": cron_id,
        "name": name or prompt[:30],
        "cron": cron_expr,
        "prompt": prompt,
        "work_dir": work_dir,
        "enabled": True,
        "silent_on_success": False,
    }
    crons.append(entry)
    _save_crons(crons)
    # Register with scheduler if running
    if _scheduler:
        _register_job(entry)
    return cron_id


def remove_cron(cron_id: str) -> bool:
    crons = _load_crons()
    original_len = len(crons)
    crons = [c for c in crons if c["id"] != cron_id]
    if len(crons) == original_len:
        return False
    _save_crons(crons)
    if _scheduler:
        try:
            _scheduler.remove_job(cron_id)
        except Exception:
            pass
    return True


def toggle_cron(cron_id: str) -> bool | None:
    crons = _load_crons()
    for c in crons:
        if c["id"] == cron_id:
            c["enabled"] = not c.get("enabled", True)
            _save_crons(crons)
            if _scheduler:
                if c["enabled"]:
                    _register_job(c)
                else:
                    try:
                        _scheduler.remove_job(cron_id)
                    except Exception:
                        pass
            return c["enabled"]
    return None


def _register_job(entry: dict):
    if not _scheduler or not entry.get("enabled", True):
        return
    try:
        parts = entry["cron"].split()
        if len(parts) == 5:
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        else:
            logger.warning("잘못된 크론 표현식: %s", entry["cron"])
            return

        _scheduler.add_job(
            _run_cron_job,
            trigger=trigger,
            id=entry["id"],
            replace_existing=True,
            kwargs={"entry": entry},
        )
        logger.info("크론잡 등록: %s (%s)", entry["id"], entry["cron"])
    except Exception:
        logger.exception("크론잡 등록 실패: %s", entry["id"])


async def _run_cron_job(entry: dict):
    from claude.runner import run_claude
    from db.store import save_execution

    logger.info("크론잡 실행: %s", entry["id"])
    work_dir = os.path.expanduser(entry.get("work_dir", "~"))
    result = await run_claude(entry["prompt"], work_dir)

    await save_execution(
        source="cron",
        prompt=entry["prompt"],
        result=result.get("result"),
        duration_sec=result["duration"],
        work_dir=work_dir,
        status=result["status"],
        error_message=result.get("error"),
        cron_id=entry["id"],
    )

    # Send result via telegram
    if _send_telegram_func:
        silent = entry.get("silent_on_success", False)
        if silent and result["status"] == "success":
            return
        text = result.get("result") or result.get("error") or "(응답 없음)"
        msg = f"⏰ 크론잡 `{entry['id']}` ({entry.get('name', '')}):\n\n{text}"
        await _send_telegram_func(msg)


def init_scheduler(send_func=None):
    global _scheduler, _send_telegram_func
    _send_telegram_func = send_func
    _scheduler = AsyncIOScheduler()
    # Register all enabled crons
    for entry in _load_crons():
        if entry.get("enabled", True):
            _register_job(entry)
    _scheduler.start()
    logger.info("스케줄러 시작됨")
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("스케줄러 종료됨")
        _scheduler = None

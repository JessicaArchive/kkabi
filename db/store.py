import aiosqlite
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "assistant.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    cron_id TEXT,
    prompt TEXT NOT NULL,
    result TEXT,
    duration_sec REAL,
    work_dir TEXT,
    status TEXT NOT NULL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    work_dir TEXT,
    duration_sec REAL
);
"""


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def save_execution(
    source: str,
    prompt: str,
    result: str | None,
    duration_sec: float,
    work_dir: str,
    status: str,
    error_message: str | None = None,
    cron_id: str | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO executions
               (timestamp, source, cron_id, prompt, result, duration_sec, work_dir, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                source,
                cron_id,
                prompt,
                result,
                duration_sec,
                work_dir,
                status,
                error_message,
            ),
        )
        await db.commit()


async def save_conversation(
    user_message: str,
    assistant_response: str,
    work_dir: str,
    duration_sec: float,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO conversations
               (timestamp, user_message, assistant_response, work_dir, duration_sec)
               VALUES (?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                user_message,
                assistant_response,
                work_dir,
                duration_sec,
            ),
        )
        await db.commit()


async def get_recent_conversations(n: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]


async def get_recent_executions(n: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM executions ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]

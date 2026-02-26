import os
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "memory")
MEMORY_PATH = os.path.join(DATA_DIR, "MEMORY.md")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")


def _ensure_dirs():
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def load_memory() -> str:
    _ensure_dirs()
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def save_memory(content: str):
    _ensure_dirs()
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def append_to_memory(text: str):
    current = load_memory()
    if current and not current.endswith("\n"):
        current += "\n"
    current += f"- {text}\n"
    save_memory(current)


def log_conversation(user_message: str, assistant_response: str):
    _ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOGS_DIR, f"{today}.md")
    time_str = datetime.now().strftime("%H:%M")
    trimmed_response = assistant_response[:200]
    if len(assistant_response) > 200:
        trimmed_response += "..."
    entry = f"## {time_str}\n**나:** {user_message}\n**Claude:** {trimmed_response}\n\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def clear_today_log():
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(LOGS_DIR, f"{today}.md")
    if os.path.exists(log_path):
        os.remove(log_path)
        return True
    return False


def cleanup_old_logs(retention_days: int = 30):
    _ensure_dirs()
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for fname in os.listdir(LOGS_DIR):
        if not fname.endswith(".md"):
            continue
        try:
            date_str = fname.replace(".md", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                os.remove(os.path.join(LOGS_DIR, fname))
                removed += 1
        except ValueError:
            continue
    return removed


def get_memory_summary() -> str:
    content = load_memory()
    if not content:
        return "(메모리 없음)"
    if len(content) > 2000:
        return content[:2000] + "\n...(생략)"
    return content

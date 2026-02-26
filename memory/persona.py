import os

PERSONA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "persona")

VALID_NAMES = {"soul", "user", "mood"}


def _ensure_dir():
    os.makedirs(PERSONA_DIR, exist_ok=True)


def load_persona_file(name: str) -> str:
    """Read SOUL.md, USER.md, or MOOD.md."""
    name = name.lower()
    if name not in VALID_NAMES:
        return ""
    _ensure_dir()
    path = os.path.join(PERSONA_DIR, f"{name.upper()}.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_persona_file(name: str, content: str):
    """Write SOUL.md, USER.md, or MOOD.md."""
    name = name.lower()
    if name not in VALID_NAMES:
        return
    _ensure_dir()
    path = os.path.join(PERSONA_DIR, f"{name.upper()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_persona_block() -> str:
    """Assemble [SOUL], [USER], [MOOD] sections into a single block."""
    sections = []
    for name in ("soul", "user", "mood"):
        content = load_persona_file(name)
        if content:
            tag = name.upper()
            sections.append(f"[{tag}]\n{content}")
    if not sections:
        return ""
    return "\n\n".join(sections)

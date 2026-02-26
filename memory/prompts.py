from memory.manager import get_memory_summary


def build_memory_block() -> str:
    summary = get_memory_summary()
    if summary == "(메모리 없음)":
        return ""
    return f"[메모리 요약]\n{summary}"


def build_conversation_block(recent_turns: list[dict]) -> str:
    if not recent_turns:
        return ""
    lines = ["[최근 대화]"]
    for turn in recent_turns:
        user_msg = turn.get("user_message", "")
        assistant_msg = turn.get("assistant_response", "")
        lines.append(f"나: {user_msg}")
        lines.append(f"Claude: {assistant_msg}")
    return "\n".join(lines)

import os
from memory.prompts import build_memory_block, build_conversation_block
from memory.persona import build_persona_block
from db.store import get_recent_conversations

SYSTEM_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "system_prompt.txt"
)

DEFAULT_SYSTEM_PROMPT = """너는 나의 개인 AI 비서다.
항상 한국어로 답변하고, 간결하게 핵심만 말해.
파일을 수정하거나 코드를 작성할 때는 바로 실행해.
기억해야 할 것이 있으면 data/memory/MEMORY.md에 기록해.
작업 완료 후에는 결과를 간단히 요약해줘."""


def load_system_prompt() -> str:
    if os.path.exists(SYSTEM_PROMPT_PATH):
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return DEFAULT_SYSTEM_PROMPT


def save_system_prompt(prompt: str):
    os.makedirs(os.path.dirname(SYSTEM_PROMPT_PATH), exist_ok=True)
    with open(SYSTEM_PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(prompt)


async def build_full_prompt(user_message: str, max_turns: int = 5) -> str:
    system_prompt = load_system_prompt()
    memory_block = build_memory_block()
    recent = await get_recent_conversations(max_turns)
    conversation_block = build_conversation_block(recent)

    persona_block = build_persona_block()

    parts = [f"[시스템] {system_prompt}"]
    if persona_block:
        parts.append(f"\n{persona_block}")
    if memory_block:
        parts.append(f"\n{memory_block}")
    if conversation_block:
        parts.append(f"\n{conversation_block}")
    parts.append(f"\n[현재 메시지]\n{user_message}")

    return "\n".join(parts)

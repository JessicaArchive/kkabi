import asyncio
import time
import logging

logger = logging.getLogger(__name__)

# Currently running Claude processes, keyed by chat_id
running_tasks: dict[int, asyncio.subprocess.Process] = {}


async def run_claude(prompt: str, work_dir: str, timeout_sec: int = 300, chat_id: int | None = None) -> dict:
    """Run Claude Code CLI and return result dict."""
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        if chat_id is not None:
            running_tasks[chat_id] = proc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            duration = time.time() - start
            return {
                "status": "timeout",
                "result": None,
                "error": f"타임아웃: {timeout_sec}초 초과",
                "duration": duration,
            }
        finally:
            if chat_id is not None:
                running_tasks.pop(chat_id, None)

        duration = time.time() - start
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            error_info = classify_error(stderr_text)
            return {
                "status": error_info["status"],
                "result": None,
                "error": error_info["message"],
                "duration": duration,
            }

        result_text = stdout.decode("utf-8", errors="replace").strip()
        return {
            "status": "success",
            "result": result_text,
            "error": None,
            "duration": duration,
        }

    except FileNotFoundError:
        duration = time.time() - start
        return {
            "status": "error",
            "result": None,
            "error": "claude CLI가 설치되지 않았습니다. `npm install -g @anthropic-ai/claude-code`로 설치하세요.",
            "duration": duration,
        }
    except Exception as e:
        duration = time.time() - start
        logger.exception("Claude 실행 중 예외")
        return {
            "status": "error",
            "result": None,
            "error": f"예기치 않은 오류: {e}",
            "duration": duration,
        }


def classify_error(stderr: str) -> dict:
    lower = stderr.lower()
    if "auth" in lower or "login" in lower:
        return {"status": "error", "message": "인증 만료. 서버에서 `claude login`을 다시 실행하세요."}
    if "rate limit" in lower or "rate_limit" in lower:
        return {"status": "rate_limited", "message": "API 한도 초과. 잠시 후 재시도합니다."}
    if "mcp" in lower:
        return {"status": "error", "message": f"MCP 서버 연결 실패: {stderr[:200]}"}
    return {"status": "error", "message": stderr[:500] if stderr else "알 수 없는 오류"}


async def cancel_task(chat_id: int) -> bool:
    proc = running_tasks.get(chat_id)
    if proc and proc.returncode is None:
        proc.kill()
        await proc.wait()
        running_tasks.pop(chat_id, None)
        return True
    return False


def is_running(chat_id: int) -> bool:
    proc = running_tasks.get(chat_id)
    return proc is not None and proc.returncode is None

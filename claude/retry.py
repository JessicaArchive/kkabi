import asyncio
import logging

logger = logging.getLogger(__name__)

RETRY_DELAY_SEC = 300  # 5 minutes
MAX_RETRIES = 3


class RetryQueue:
    def __init__(self):
        self._pending: list[dict] = []

    async def schedule_retry(self, run_func, prompt: str, work_dir: str, callback, attempt: int = 1):
        if attempt > MAX_RETRIES:
            logger.warning("최대 재시도 횟수 초과: %s", prompt[:50])
            await callback(None, f"최대 재시도 횟수({MAX_RETRIES}회) 초과")
            return

        logger.info("재시도 예약 (%d/%d), %d초 후: %s", attempt, MAX_RETRIES, RETRY_DELAY_SEC, prompt[:50])
        await asyncio.sleep(RETRY_DELAY_SEC)

        result = await run_func(prompt, work_dir)

        if result["status"] == "rate_limited":
            await self.schedule_retry(run_func, prompt, work_dir, callback, attempt + 1)
        else:
            await callback(result, None)


retry_queue = RetryQueue()

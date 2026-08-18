"""Retry with exponential backoff for transient HTTP failures.

Same rationale as originally applied to the eval's call into the demo
backend, now also used by the judge LLM provider calls (math_eval/llm_provider.py):
evalite's ConversationRunner deliberately does not catch per-case exceptions
(it gathers all conversations via a bare asyncio.gather with no
return_exceptions=True), so one uncaught transient failure on one
conversation takes down the entire run. Retrying transient errors —
including 429 (rate limiting, the common case on free-tier LLM API keys
under this eval's concurrency) — is this adapter/provider's job per
evalite's design; resilience is left to the implementor, not provided by
the framework itself.

Configurable via env vars (read lazily, at call time, not at import time —
this module is imported before run_eval.py's load_dotenv() runs, so
resolving eagerly at module or default-argument level would read stale
unset values):

    RETRY_MAX_ATTEMPTS         default 3
    RETRY_BASE_DELAY_SECONDS   default 1.0

Explicit max_attempts/base_delay arguments to with_retry() always win over
the env vars, for call sites that want to opt out of one-size-fits-all
tuning.
"""

import asyncio
import os
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

T = TypeVar("T")


def _default_max_attempts() -> int:
    return int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))


def _default_base_delay() -> float:
    return float(os.environ.get("RETRY_BASE_DELAY_SECONDS", "1.0"))


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int | None = None,
    base_delay: float | None = None,
) -> T:
    if max_attempts is None:
        max_attempts = _default_max_attempts()
    if base_delay is None:
        base_delay = _default_base_delay()

    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await func()
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRYABLE_STATUS_CODES:
                raise
            last_exc = e
        except httpx.TransportError as e:
            last_exc = e

        if attempt < max_attempts - 1:
            delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc

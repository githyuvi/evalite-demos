"""AgentAdapter wrapping math-solver-agent's backend (/api/query).

evalite's ConversationRunner calls `adapter.send(messages)` with the FULL
running history each turn (not just the latest message), while the demo
backend tracks history itself server-side, keyed by `conversation_id`
(see demo-agent-app/math-solver-agent/backend/storage.py) and only needs
the newest message each call. This adapter bridges the two: it sends only
`messages[-1]`, and remembers which backend `conversation_id` belongs to
which evalite conversation.

Concurrency note: a single adapter instance is shared across every
case/iteration ConversationRunner runs (possibly many concurrently, bounded
by max_workers). Each conversation gets its own `history` list object,
freshly created once and mutated in place for that conversation's whole
lifetime (see evalite/runner/conversation_runner.py) — so `id(messages)`
is a safe, collision-free key for the lifetime of one run, without needing
any explicit conversation-start signal from the Protocol.
"""

import httpx
from evalite import AgentResponse

from .constants import SYSTEM_FAILURE_PREFIX
from .retry import with_retry


class MathSolverDemoAdapter:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self._base_url = base_url
        self._client = httpx.AsyncClient(timeout=120)
        self._conversation_ids: dict[int, str] = {}

    async def send(self, messages: list[dict]) -> AgentResponse:
        key = id(messages)
        conversation_id = self._conversation_ids.get(key)
        last_message = messages[-1]["content"]

        async def _do_request() -> dict:
            resp = await self._client.post(
                f"{self._base_url}/api/query",
                json={"message": last_message, "conversation_id": conversation_id},
            )
            resp.raise_for_status()
            return resp.json()

        # A transient 5xx/network blip on one conversation shouldn't fail
        # the whole run — see retry.py's docstring for why this lives here
        # rather than in evalite itself or in math-solver-agent (which is
        # the system under test; retrying inside it would mask the exact
        # failure behavior the eval is supposed to measure). The backend's
        # own idempotency guard (main.py's _append_user_turn_idempotent)
        # makes a retry of the same conversation_id + message safe — it
        # won't duplicate the user turn if the prior attempt's LLM call
        # failed after the append already happened.
        try:
            data = await with_retry(_do_request)
        except Exception as e:  # noqa: BLE001 — a persistently failing backend must not crash the
            # whole run via evalite's uncaught-per-case asyncio.gather (see
            # retry.py's docstring). Surface it as a turn instead, tagged so
            # driver.py stops immediately and scorer.py/iteration_stats.py
            # can exclude it from quality aggregates rather than reading it
            # as a genuine zero score.
            return AgentResponse(
                content=f"{SYSTEM_FAILURE_PREFIX} agent backend request failed: {e}",
                metadata={"conversation_id": conversation_id, "system_failure": True},
            )

        self._conversation_ids[key] = data["conversation_id"]
        return AgentResponse(
            content=data["message"]["content"],
            metadata={"conversation_id": data["conversation_id"]},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

"""MathTutorDriver: a ConversationDriver that retries a wrong or poorly-
justified answer without ever revealing the correct one.

Per the eval's requirement: if the math agent's answer is wrong, tell it
the answer is wrong (not what the right answer is); if its steps are
missing or don't hold together, tell it to redo them.

Feedback deliberately never confirms answer correctness when the steps are
invalid: if the agent were told "your answer is right, just show better
steps," it would have every incentive to keep that answer fixed and hunt
for *any* derivation that reaches it, rather than actually re-deriving the
solution — the judge would then be grading post-hoc rationalization, not
reasoning. So the "final answer is not correct" message only ever fires
when the steps are independently judged valid (see `next_message`).

Stateless by design: `_retries_used` is derived from `history` (count of
prior assistant turns) rather than an instance counter, because a single
driver instance is shared across all `iterations` of one ConversationTestCase
and those iterations run concurrently (ConversationRunner gathers them) —
an instance-mutable counter would race across iterations sharing this driver.
"""

import json

from .answer_extraction import has_reasoning_steps
from .constants import SYSTEM_FAILURE_PREFIX
from .marking import score_answer
from .step_validator import validate_steps


class MathTutorDriver:
    def __init__(
        self,
        expected_spec_json: str,
        provider,
        cache: dict | None = None,
        max_retries: int = 2,
    ) -> None:
        spec = json.loads(expected_spec_json)
        self._section = spec["section"]
        self._answer_spec = spec["answer"]
        self._provider = provider
        self._cache = cache
        self._max_retries = max_retries

    def _retries_used(self, history: list[dict]) -> int:
        return sum(1 for m in history if m["role"] == "assistant") - 1

    async def _diagnose(self, history: list[dict], response: str) -> tuple[bool, bool, bool]:
        """Returns (answer_correct, steps_shown, steps_valid).

        `question_text` comes from `history[0]` — the very first user turn
        is always the original question, unlike `should_continue`'s
        `response`/later turns which are the driver's own retry feedback.
        """
        question_text = history[0]["content"]
        points, max_points, _explanation, answered, _strategy = await score_answer(
            self._section,
            self._answer_spec,
            response,
            provider=self._provider,
            question_text=question_text,
            cache=self._cache,
        )
        answer_correct = answered and points == max_points

        judge_result = await validate_steps(
            self._provider, question_text, response, cache=self._cache
        )
        steps_shown = judge_result["steps_shown"] or has_reasoning_steps(response)
        steps_valid = judge_result["steps_valid"]

        return answer_correct, steps_shown, steps_valid

    async def should_continue(self, history: list[dict], response: str) -> bool:
        if response.startswith(SYSTEM_FAILURE_PREFIX):
            # A persistently failing backend won't be fixed by retrying at
            # the conversation level — stop immediately rather than burning
            # the retry budget on a dead endpoint.
            return False
        if self._retries_used(history) >= self._max_retries:
            return False
        answer_correct, _steps_shown, steps_valid = await self._diagnose(history, response)
        return not (answer_correct and steps_valid)

    async def next_message(self, history: list[dict], response: str) -> str:
        answer_correct, steps_shown, steps_valid = await self._diagnose(history, response)

        parts = []
        if not steps_shown:
            parts.append(
                "You didn't show your step-by-step working. Please show your "
                "full reasoning/derivation, not just a final answer."
            )
        elif not steps_valid:
            parts.append(
                "Your reasoning didn't hold together — it wasn't clear or "
                "logically consistent. Please rework your derivation from "
                "scratch, step by step."
            )

        # Only ever mention the final answer's correctness once we already
        # know the steps are valid — see module docstring for why this
        # can't fire alongside the steps-invalid branch above.
        if steps_valid and not answer_correct:
            parts.append(
                "Your final answer is not correct. Please re-check your "
                "work carefully and try again."
            )

        if not parts:
            parts.append("Please double check your work and try again.")

        return " ".join(parts)

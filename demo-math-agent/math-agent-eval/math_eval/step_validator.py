"""LLM judge for step-by-step reasoning quality — independent of whether the
final answer is correct.

This is what implements the "validate steps" half of scoring: JEE's own
answer key only ever grades the final option/value, but a math agent could
land on the right option by a lucky guess with a bogus derivation, or a
wrong option despite mostly-sound reasoning. Both are useful signals an
eval should distinguish, which a bare answer-key comparison can't do.

`cache` (optional): when the same `response_text` is validated twice in one
turn — once by `driver.MathTutorDriver`'s continuation diagnosis, once by
`scorer.JEEConversationScorer`'s actual scoring — passing a shared dict lets
the second call reuse the first's result instead of making a second judge
call (which would also risk the two callers disagreeing on `steps_valid`
for the same response, since judge output isn't perfectly deterministic).
"""

import json

from . import judge_audit

_STEP_JUDGE_SYSTEM_PROMPT = (
    "You are grading the WORKING SHOWN in a math/physics solution, not "
    "whether the final answer is correct. Given the question and a "
    "candidate's full response, decide:\n"
    "1. steps_shown: true if the response shows genuine step-by-step "
    "reasoning/derivation (not just a bare final answer with no working).\n"
    "2. steps_valid: true if the shown steps are mathematically sound and "
    "logically lead to the response's own stated final answer (internal "
    "consistency) — false if there is a clear mathematical error, "
    "unjustified leap, or non-sequitur in the derivation, even if the "
    "final answer happens to be correct.\n\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"steps_shown": true or false, "steps_valid": true or false, '
    '"explanation": "one sentence"}'
)


async def validate_steps(
    provider, question_text: str, response_text: str, *, cache: dict | None = None
) -> dict:
    """Ask the judge provider to assess the response's reasoning quality.

    Degrades gracefully (steps_shown=False, steps_valid=False,
    judge_error=True) on any judge-call or parse failure — this must never
    raise, since evalite's ConversationRunner doesn't catch per-case
    exceptions (one uncaught failure would crash the entire run's
    asyncio.gather, per retry.py's docstring). `judge_error` distinguishes
    "the judge call itself misbehaved" from "the judge reviewed the
    response and genuinely found it invalid" (gap #5) — both used to look
    identical in stored data.
    """
    cache_key = ("steps", response_text)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    messages = [
        {"role": "system", "content": _STEP_JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Question:\n{question_text}\n\nCandidate's response:\n{response_text}",
        },
    ]

    try:
        completion = await provider.complete(messages)
        parsed = json.loads(completion)
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object")
        result = {
            "steps_shown": bool(parsed.get("steps_shown", False)),
            "steps_valid": bool(parsed.get("steps_valid", False)),
            "explanation": str(parsed.get("explanation", "")),
            "judge_error": False,
        }
        judge_audit.log("validate_steps", question_text, response_text, completion, result)
    except Exception as e:  # noqa: BLE001 — judge outage/malformed output must degrade, never crash the run
        result = {
            "steps_shown": False,
            "steps_valid": False,
            "explanation": f"judge call failed: {e}",
            "judge_error": True,
        }
        judge_audit.log("validate_steps", question_text, response_text, "", result)

    if cache is not None:
        cache[cache_key] = result
    return result

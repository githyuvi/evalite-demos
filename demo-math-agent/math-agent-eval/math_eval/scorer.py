"""JEEConversationScorer: evalite Scorer combining JEE's section-specific
marking scheme (final-answer correctness) with an LLM-judged steps-quality
signal, per turn.

`expected` arrives from ConversationRunner as `{"outcomes": [...]}`
(evalite/runner/conversation_runner.py hardcodes that key). We pack a
single JSON string into `expected_outcomes` (see build_test_cases.py)
holding `{"section": int, "answer": answer_spec, "question_text": str}` and
parse it back out here — the cleanest way to carry structured,
section-specific ground truth through a `list[str]` field designed for flat
outcome strings.

`question_text` is read from this spec rather than the `input` parameter
`scorer.score()` receives: `input` is `turn_input`, which on turn 0 is the
real question but on retry turns is the driver's own generic feedback
message ("Your final answer is not correct...") — using that as the judge's
"question" would silently feed the judge the wrong context past turn 0.

Score.value formula: 70% final-answer correctness + 30% steps quality
(1.0 valid, 0.5 shown-but-invalid, 0.0 missing). The answer-correctness
component is `marking.rescaled_fraction`, not plain points/max_points —
see that function's docstring for why (JEE negative marking needs to be
visible in the score, not clamped away). `passed` requires BOTH full marks
AND valid steps — a lucky guess with bogus reasoning should not read as a
clean pass.
"""

import json

from evalite import Score

from .answer_extraction import has_reasoning_steps
from .constants import SYSTEM_FAILURE_PREFIX
from .marking import rescaled_fraction, score_answer
from .step_validator import validate_steps

_ANSWER_WEIGHT = 0.7
_STEPS_WEIGHT = 0.3


class JEEConversationScorer:
    def __init__(self, provider, cache: dict | None = None) -> None:
        self._provider = provider
        self._cache = cache

    async def score(self, input: str, expected: dict, actual) -> Score:
        if actual.metadata.get("system_failure"):
            return Score(
                passed=False,
                value=0.0,
                reasoning=f"{SYSTEM_FAILURE_PREFIX} {actual.content}",
            )

        spec = json.loads(expected["outcomes"][0])
        section = spec["section"]
        answer_spec = spec["answer"]
        question_text = spec["question_text"]

        points, max_points, marking_explanation, _answered, extract_strategy = await score_answer(
            section, answer_spec, actual.content,
            provider=self._provider, question_text=question_text, cache=self._cache,
        )
        steps_shown_heuristic = has_reasoning_steps(actual.content)

        judge_result = await validate_steps(
            self._provider, question_text, actual.content, cache=self._cache
        )
        steps_shown = judge_result["steps_shown"] or steps_shown_heuristic
        steps_valid = judge_result["steps_valid"]

        answer_fraction = rescaled_fraction(section, points, max_points)
        steps_fraction = 1.0 if steps_valid else (0.5 if steps_shown else 0.0)
        value = max(0.0, min(1.0, _ANSWER_WEIGHT * answer_fraction + _STEPS_WEIGHT * steps_fraction))

        full_marks = points == max_points
        passed = full_marks and steps_valid

        judge_note = " [JUDGE_ERROR]" if judge_result.get("judge_error") else ""
        reasoning = (
            f"[Section {section}] {marking_explanation}. "
            f"Answer extraction strategy: {extract_strategy}. "
            f"Steps: shown={steps_shown}, valid={steps_valid}{judge_note} ({judge_result['explanation']})."
        )

        return Score(passed=passed, value=value, reasoning=reasoning)

"""Builds the run-detail response the frontend's overview + per-case
accordion view needs, on top of the flat `RunResult.case_results` list
`SqliteStorage.get_run()` returns.

Reuses math_eval's own aggregation/constants modules (`iteration_stats.py`,
`constants.py`, `questions.py`) rather than re-deriving the same logic
here. This module now lives inside `math-agent-eval` itself (moved from
the formerly-separate `math-agent-eval-ui/backend`), so `math_eval` is
imported directly as a sibling package — no `sys.path` hack needed
anymore.
"""

import re

from math_eval.constants import SYSTEM_FAILURE_PREFIX
from math_eval.iteration_stats import (
    build_case_series,
    build_turn_series,
    overall_average_score,
    per_iteration_averages,
    per_iteration_failure_counts,
    per_turn_averages,
)
from math_eval.questions import QUESTIONS

_QUESTIONS_BY_ID = {q.id: q for q in QUESTIONS}

SCORE_FORMULA_DESCRIPTION = (
    "value = 0.7 × answer_fraction + 0.3 × steps_fraction, where "
    "answer_fraction rescales this question's JEE point range (full marks "
    "to negative marking) onto [0, 1] so a confident wrong answer scores "
    "below an unanswered one, and steps_fraction is 1.0 (judge: valid) / "
    "0.5 (shown but invalid) / 0.0 (missing). `passed` requires full marks "
    "AND valid steps."
)

_ITER_SUFFIX_RE = re.compile(r"^(.*)\[iter=(\d+)\]$")


def _split_case_id(case_id: str) -> tuple[str, int]:
    match = _ITER_SUFFIX_RE.match(case_id)
    if not match:
        return case_id, 0
    return match.group(1), int(match.group(2))


def _is_failure(reasoning: str) -> bool:
    # Substring, not startswith: on a FINAL row, FinalTurnAccumulator
    # (accumulator.py) has already wrapped the marker inside "Final turn
    # score after N turn(s): ...", so it's no longer at position 0.
    return SYSTEM_FAILURE_PREFIX in reasoning


def _format_expected_answer(answer_spec: dict) -> str:
    answer_type = answer_spec["type"]
    if answer_type == "single":
        return answer_spec["correct"]
    if answer_type == "multi":
        return ", ".join(sorted(answer_spec["correct"]))
    if answer_type == "numeric":
        if "range" in answer_spec:
            lo, hi = answer_spec["range"]
            return f"[{lo:g}, {hi:g}]"
        return f"{answer_spec['exact']:g}"
    return str(answer_spec)


def build_overview(case_results, threshold: float) -> dict:
    # A "case" is one question, not one (question, iteration) pair — 8
    # questions x 3 independent iterations must report as 8 cases, not 24.
    # Each iteration is a fully separate, independent repeat of the whole
    # conversation (for measuring consistency), not a continuation of the
    # previous one, so a case's representative score is its LAST
    # iteration's score — same convention `overall_average_score` already
    # uses — and a case counts as failed if ANY of its iterations hit a
    # system failure.
    series = build_case_series(case_results)
    total = len(series)
    failed = sum(1 for s in series if any(is_failure for _, _, is_failure in s.points))
    above = sum(
        1
        for s in series
        if s.points
        and not any(is_failure for _, _, is_failure in s.points)
        and s.points[-1][1] >= threshold
    )
    below = total - failed - above

    per_iter_avg = per_iteration_averages(series)
    per_iter_fail = per_iteration_failure_counts(series)
    overall = overall_average_score(series)

    # Turn depth (0, 1, 2, ...) is a different axis from iteration (1, 2, 3
    # above): iterations are independent repeats of a question, turns are
    # retries *within* one of those repeats. Kept 0-indexed here, matching
    # how individual turns are already labeled elsewhere ("Turn 0", "Turn
    # 1", ...), unlike the 1-indexed-for-display iterations.
    turn_series = build_turn_series(case_results)
    turn_avg = per_turn_averages(turn_series)

    return {
        "total_cases": total,
        "failed_cases": failed,
        "above_threshold": above,
        "below_threshold": below,
        "threshold": threshold,
        # 1-indexed for display — iteration_stats.py's indices are 0-based
        # internally, matching conversation_runner.py's range(iterations).
        "per_iteration_average": {str(i + 1): v for i, v in sorted(per_iter_avg.items())},
        "per_iteration_failure_counts": {
            str(i + 1): v for i, v in sorted(per_iter_fail.items())
        },
        "per_turn_average": {str(t): v for t, v in sorted(turn_avg.items())},
        "overall_average_score": overall,
        "score_formula": SCORE_FORMULA_DESCRIPTION,
    }


def build_case_detail(case_results) -> list[dict]:
    by_base: dict[str, dict[int, list]] = {}
    for cr in case_results:
        base_id, iter_idx = _split_case_id(cr.case_id)
        by_base.setdefault(base_id, {}).setdefault(iter_idx, []).append(cr)

    cases = []
    for base_id in sorted(by_base):
        question = _QUESTIONS_BY_ID.get(base_id)
        iterations = []
        for iter_idx in sorted(by_base[base_id]):
            group = by_base[base_id][iter_idx]
            turns = sorted((cr for cr in group if cr.iteration != -1), key=lambda c: c.iteration)
            final = next((cr for cr in group if cr.iteration == -1), None)
            is_failure = bool(final and _is_failure(final.score.reasoning))

            iterations.append(
                {
                    "iteration": iter_idx,
                    "system_failure": is_failure,
                    "turns": [
                        {
                            "turn": t.iteration,
                            "input": t.input,
                            "output": t.actual,
                            "score": t.score.value,
                            "passed": t.passed,
                        }
                        for t in turns
                    ],
                    "final_score": final.score.value if final else None,
                    "final_passed": final.passed if final else None,
                    "final_reasoning": final.score.reasoning if final else None,
                }
            )

        cases.append(
            {
                "base_case_id": base_id,
                "question_text": question.text if question else None,
                "section": question.section if question else None,
                "expected_answer": (
                    _format_expected_answer(question.answer_spec) if question else None
                ),
                "iterations": iterations,
            }
        )
    return cases


def build_case_pass_summary(case_results) -> dict:
    """Case-level (not per-turn, not per-iteration) pass/fail counts, for
    the runs list — evalite's own `RunResult.passed`/`.failed` count every
    `CaseResult` row (every turn attempt *and* every FINAL row, across all
    iterations), so 8 questions x 3 iterations reports as up to ~66 rows,
    not 8. That's a different, more granular denominator than "cases" and
    was confusing side-by-side with the per-case overview below it.

    A case's outcome here is its LAST iteration's `passed` (full marks AND
    valid steps) — same "last iteration is representative" convention as
    `build_overview`/`overall_average_score` — unless any iteration hit a
    system failure, in which case the case is counted as a system failure
    rather than pass/fail.
    """
    cases = build_case_detail(case_results)
    passed = failed = system_failure = 0
    for case in cases:
        iterations = case["iterations"]
        if not iterations:
            continue
        if any(it["system_failure"] for it in iterations):
            system_failure += 1
        elif iterations[-1]["final_passed"]:
            passed += 1
        else:
            failed += 1

    return {
        "total_cases": len(cases),
        "cases_passed": passed,
        "cases_failed": failed,
        "cases_system_failure": system_failure,
    }

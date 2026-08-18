"""Cross-iteration aggregation (gap #7 in GAPS_AND_IMPROVEMENTS.md).

`iterations=N` in build_test_cases.py repeats each question's whole
conversation N times independently, simulating how a real user would
re-query an agent: sometimes it nails everything, sometimes it's wrong or
unsatisfactory and the user (here, `MathTutorDriver`) pushes back. Nothing
previously rolled those N repeats into a per-question or per-run summary —
each repeat's FINAL row just sat flat in `case_results`, distinguishable
only by parsing the `[iter=N]` suffix evalite bakes into `case_id`
(conversation_runner.py:124-126) — which is exactly what this module does,
then aggregates on top of it.

Terminology: a "case" here means one *question* (`ConversationTestCase.id`),
not one (case, iteration) pair. Each case's `iterations` independent
conversations each produce one FINAL row (`CaseResult.iteration == -1`);
this module builds one ordered series per case from those FINAL rows.

Failure handling: a system failure (see constants.py) is a broken
conversation, not a real quality signal. Including its 0.0 in a "how good
was the agent" average would be as misleading as clamping negative JEE
marks to 0 (gap #8) — so failures are excluded from every numeric average
here, but still counted per iteration position via
`per_iteration_failure_counts` so they stay visible rather than being
silently dropped from the report.
"""

import re
from dataclasses import dataclass

from .constants import SYSTEM_FAILURE_PREFIX

_ITER_SUFFIX_RE = re.compile(r"^(.*)\[iter=(\d+)\]$")


@dataclass
class CaseIterationSeries:
    base_case_id: str
    # (iteration_index, score_value, is_failure), ordered by iteration_index.
    # iteration_index is 0-based, matching conversation_runner.py's
    # `range(case.iterations)` — display code should add 1 for humans.
    points: list[tuple[int, float, bool]]


def _split_case_id(case_id: str) -> tuple[str, int]:
    """`"section3_q8[iter=1]"` -> `("section3_q8", 1)`.

    A case run with `iterations == 1` has no `[iter=N]` suffix at all
    (conversation_runner.py:124-126 only adds it when `iterations != 1`) —
    treated as iteration index 0.
    """
    match = _ITER_SUFFIX_RE.match(case_id)
    if not match:
        return case_id, 0
    return match.group(1), int(match.group(2))


def build_case_series(case_results) -> list[CaseIterationSeries]:
    """One series per base case, built from FINAL (iteration == -1) rows only."""
    by_base: dict[str, list[tuple[int, float, bool]]] = {}
    for cr in case_results:
        if cr.iteration != -1:
            continue
        base_id, iter_index = _split_case_id(cr.case_id)
        # Substring, not startswith: FinalTurnAccumulator.finalize() (see
        # accumulator.py) wraps a turn's reasoning as "Final turn score
        # after N turn(s): <original reasoning>" before it ever reaches
        # this FINAL row (iteration == -1) — so on a system-failure turn,
        # SYSTEM_FAILURE_PREFIX is no longer at position 0. A pure
        # startswith() here silently misclassified every failed run as a
        # genuine (very low) score instead of excluding it.
        is_failure = SYSTEM_FAILURE_PREFIX in cr.score.reasoning
        by_base.setdefault(base_id, []).append((iter_index, cr.score.value, is_failure))

    return [
        CaseIterationSeries(base_case_id=base_id, points=sorted(points))
        for base_id, points in sorted(by_base.items())
    ]


def per_iteration_averages(series: list[CaseIterationSeries]) -> dict[int, float]:
    """Average score at each iteration position, across every case that has
    a non-failure result at that position.
    """
    buckets: dict[int, list[float]] = {}
    for s in series:
        for iter_index, value, is_failure in s.points:
            if is_failure:
                continue
            buckets.setdefault(iter_index, []).append(value)
    return {i: sum(vals) / len(vals) for i, vals in sorted(buckets.items())}


def per_iteration_failure_counts(series: list[CaseIterationSeries]) -> dict[int, int]:
    """How many cases hit a system failure at each iteration position — kept
    separate from `per_iteration_averages` so a failure is visible in the
    report without corrupting the quality average at that position.
    """
    counts: dict[int, int] = {}
    for s in series:
        for iter_index, _value, is_failure in s.points:
            if is_failure:
                counts[iter_index] = counts.get(iter_index, 0) + 1
    return counts


def overall_average_score(series: list[CaseIterationSeries]) -> float | None:
    """Mean of each case's LAST recorded iteration's score, over cases that
    never hit a system failure at any iteration. A case that failed even
    once is excluded entirely — its most recent recorded value would be a
    failure, not a quality signal, per the module docstring's failure
    policy. Returns None if every case failed.
    """
    finals = [
        s.points[-1][1]
        for s in series
        if s.points and not any(is_failure for _, _, is_failure in s.points)
    ]
    if not finals:
        return None
    return sum(finals) / len(finals)

"""Cross-iteration aggregation.

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


@dataclass
class ConversationTurnSeries:
    base_case_id: str
    iteration: int
    # score.value at each turn (iteration != -1) this one conversation
    # actually ran, ordered by turn index (0-based, matching how turns are
    # already labeled elsewhere — unlike the 1-indexed-for-display outer
    # iterations). Excludes system-failure conversations entirely — see
    # build_turn_series.
    turn_scores: list[float]


def build_turn_series(case_results) -> list[ConversationTurnSeries]:
    """One series per (question, iteration) conversation, built from its
    turn rows (iteration != -1) — NOT the FINAL summary row.

    System-failure conversations are dropped entirely, the same policy as
    `build_case_series`: a broken backend/judge call isn't a quality
    signal, and averaging its 0.0 in would misrepresent every turn depth
    it touches.
    """
    by_conv: dict[tuple[str, int], list[tuple[int, float]]] = {}
    failed_convs: set[tuple[str, int]] = set()

    for cr in case_results:
        if cr.iteration == -1:
            continue
        base_id, iter_index = _split_case_id(cr.case_id)
        key = (base_id, iter_index)
        by_conv.setdefault(key, []).append((cr.iteration, cr.score.value))
        if SYSTEM_FAILURE_PREFIX in cr.score.reasoning:
            failed_convs.add(key)

    return [
        ConversationTurnSeries(
            base_case_id=base_id,
            iteration=iter_index,
            turn_scores=[v for _, v in sorted(turns)],
        )
        for (base_id, iter_index), turns in sorted(by_conv.items())
        if (base_id, iter_index) not in failed_convs
    ]


def per_turn_averages(turn_series: list[ConversationTurnSeries]) -> dict[int, float]:
    """Average score at each turn depth (0, 1, 2, ...), across every
    non-failed conversation, forward-filling conversations that converged
    (or hit max_turns) before reaching that depth with their own last
    real turn's score.

    Forward-fill is deliberate, not an approximation: without it, "turn 2
    average" would only average over conversations that actually needed a
    third attempt — an ever-shrinking, retry-biased subset. That would
    trend the average *down* as depth increases for the wrong reason (only
    the hard cases are still being counted), not because later turns are
    genuinely worse. Forward-filling means every conversation contributes
    to every depth, holding its resolved value once it's done — same
    reasoning `overall_average_score` uses for "last iteration is
    representative," one level down.
    """
    series = [s.turn_scores for s in turn_series if s.turn_scores]
    if not series:
        return {}

    max_depth = max(len(s) for s in series)
    padded = [s + [s[-1]] * (max_depth - len(s)) for s in series]

    return {i: sum(p[i] for p in padded) / len(padded) for i in range(max_depth)}


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

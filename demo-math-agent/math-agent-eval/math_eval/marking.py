"""JEE (Advanced) 2025 Paper 1 marking scheme, per section — transcribed
from the section headers in math-solver-agent/2025_1_English.pdf.

  Section 1: single correct option.        +3 / 0 / -1
  Section 2: one-or-more correct options.  +4 full, partial credit for a
             correct-but-incomplete subset, 0 unanswered, -2 if any chosen
             option is wrong. Partial credit depends on how many options
             are actually correct (2, 3, or 4) — see the official example
             in the PDF under Section 2's marking scheme.
  Section 3: numerical value.               +4 / 0 (no negative marking)
  Section 4: match-the-list, single correct combination.  +4 / 0 / -1

`score_answer` returns evalite-agnostic (points, max_points, explanation,
answered, extraction_strategy) — evalite's Score.value in [0, 1] is derived
from this in scorer.py via `rescaled_fraction`, not here, so this module
stays independent of evalite's Score model.

Answer extraction (which option/value the response actually gave) now runs
through `answer_extraction.extract_answer`'s multi-strategy cascade instead
of a single regex — see that module's docstring for why.
"""

from .answer_extraction import (
    extract_answer,
    extract_multi_letters,
    extract_numeric,
    extract_single_letter,
)

SECTION_RUBRIC: dict[int, dict] = {
    1: {"type": "single", "full": 3.0, "negative": -1.0},
    2: {"type": "multi", "full": 4.0, "negative": -2.0},
    3: {"type": "numeric", "full": 4.0, "negative": 0.0},
    4: {"type": "single", "full": 4.0, "negative": -1.0},
}

# Section 2's partial-credit table: {n_correct_options: {n_chosen: points}}.
# Only reachable when every chosen option is correct but not all of them
# were chosen (a strict, non-empty subset) — see score_answer's "multi"
# branch. That's only possible when 2-4 options are correct (a 1-correct-
# option question has no non-empty proper subset to partially credit), but
# the lookup below still fails loudly rather than silently defaulting to 0
# if a question's answer_spec ever falls outside what this table covers —
# a wrong/missing entry should be a build-time authoring bug, not a
# silent mis-score.
_MULTI_PARTIAL_CREDIT = {
    4: {3: 3.0, 2: 2.0, 1: 1.0},
    3: {2: 2.0, 1: 1.0},
    2: {1: 1.0},
}


def rescaled_fraction(section: int, points: float, max_points: float) -> float:
    """Map this section's [negative, max_points] point range onto [0, 1].

    Plain `points / max_points` clamped at 0 makes "unanswered" (0 points)
    and "answered wrong, negative-marked" (negative points) score
    identically — losing JEE's own signal that a confident wrong guess is
    worse than abstaining (gap #8). Rescaling the *whole* range, including
    the negative floor, onto [0, 1] preserves that ordering while staying
    inside evalite's `Score.value >= 0` constraint (`Score.value` cannot
    literally go negative — it's a `Field(ge=0.0, le=1.0)`).

    For sections with no negative marking (negative=0), this reduces to the
    original `points / max_points` behavior.
    """
    min_points = SECTION_RUBRIC[section]["negative"]
    span = max_points - min_points
    if span <= 0:
        return max(0.0, min(1.0, points / max_points)) if max_points else 0.0
    return max(0.0, min(1.0, (points - min_points) / span))


async def score_answer(
    section: int,
    answer_spec: dict,
    response: str,
    *,
    provider,
    question_text: str,
    cache: dict | None = None,
) -> tuple[float, float, str, bool, str]:
    """Score one response against one question's answer_spec.

    Returns:
        (points_earned, max_points, explanation, answered, extraction_strategy)
        — points_earned may be negative (JEE negative marking); max_points
        is this section's full-marks value; answered is False only when no
        option/value could be extracted at all (an "unanswered" response
        under JEE's own rules never receives negative marks);
        extraction_strategy records which of `extract_answer`'s cascade
        strategies (regex/boxed/last_line/llm/none) produced the answer
        line, for auditing silent zero-scores caused by format drift.
    """
    rubric = SECTION_RUBRIC[section]
    full = rubric["full"]
    negative = rubric["negative"]

    extraction = await extract_answer(
        provider, rubric["type"], question_text, response, cache=cache
    )
    answer_line = extraction.raw
    strategy = extraction.strategy
    note = f" [extracted via {strategy}]" if answer_line else " [no answer found by any strategy]"

    if rubric["type"] == "single":
        chosen = extract_single_letter(answer_line)
        correct = answer_spec["correct"]
        if chosen is None:
            return 0.0, full, f"no option chosen -> 0 marks (unanswered){note}", False, strategy
        if chosen == correct:
            return full, full, f"chose {chosen} (correct) -> +{full:g} marks{note}", True, strategy
        return (
            negative,
            full,
            f"chose {chosen}, correct answer was {correct} -> {negative:g} marks (negative marking){note}",
            True,
            strategy,
        )

    if rubric["type"] == "multi":
        chosen = extract_multi_letters(answer_line)
        correct = set(answer_spec["correct"])
        if not chosen:
            return 0.0, full, f"no options chosen -> 0 marks (unanswered){note}", False, strategy
        if not chosen.issubset(correct):
            wrong = sorted(chosen - correct)
            return (
                negative,
                full,
                f"chose incorrect option(s) {wrong} -> {negative:g} marks (negative marking){note}",
                True,
                strategy,
            )
        if chosen == correct:
            return (
                full,
                full,
                f"chose all correct options {sorted(chosen)} -> +{full:g} marks (full marks){note}",
                True,
                strategy,
            )
        by_chosen_count = _MULTI_PARTIAL_CREDIT.get(len(correct))
        if by_chosen_count is None or len(chosen) not in by_chosen_count:
            raise ValueError(
                f"no partial-credit entry for {len(chosen)}/{len(correct)} correct options chosen "
                f"(section 2) — _MULTI_PARTIAL_CREDIT is missing this shape; fix the table rather "
                f"than silently scoring 0"
            )
        points = by_chosen_count[len(chosen)]
        return (
            points,
            full,
            f"chose {len(chosen)}/{len(correct)} correct option(s), none wrong -> "
            f"+{points:g} marks (partial credit){note}",
            True,
            strategy,
        )

    if rubric["type"] == "numeric":
        value = extract_numeric(answer_line)
        if value is None:
            return 0.0, full, f"no numeric answer given -> 0 marks (unanswered){note}", False, strategy
        rounded = round(value, 2)
        if "range" in answer_spec:
            lo, hi = answer_spec["range"]
            if lo <= rounded <= hi:
                return (
                    full,
                    full,
                    f"{rounded:g} is within the accepted range [{lo:g}, {hi:g}] -> +{full:g} marks{note}",
                    True,
                    strategy,
                )
            return (
                0.0,
                full,
                f"{rounded:g} is outside the accepted range [{lo:g}, {hi:g}] -> 0 marks{note}",
                True,
                strategy,
            )
        exact = answer_spec["exact"]
        if abs(rounded - exact) < 1e-9:
            return full, full, f"{rounded:g} matches the exact answer {exact:g} -> +{full:g} marks{note}", True, strategy
        return 0.0, full, f"{rounded:g} does not match the exact answer {exact:g} -> 0 marks{note}", True, strategy

    raise ValueError(f"unknown rubric type for section {section}")

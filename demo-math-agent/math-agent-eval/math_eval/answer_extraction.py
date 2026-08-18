"""Parses a math agent's free-text response into a structured final answer.

Originally a single regex keyed to the demo agent's documented "Answer: <x>"
convention (see backend/providers/base.py's SYSTEM_PROMPT). That's fragile:
any agent that deviates from the exact convention — "Final Answer:",
markdown-bolded "**Answer:**", or an answer that only ever appears inside a
LaTeX `\\boxed{...}` (which is how math-gpt.org's own agent formats output —
see the sibling demo's API.md) — would silently score as "unanswered" even
when the agent solved the problem correctly (gap #1/#9 in
GAPS_AND_IMPROVEMENTS.md).

`extract_answer` now runs a cascade of strategies, cheapest first, each only
attempted if the previous one failed to produce something the expected
answer type can actually parse:

  1. regex     — the "Answer:"/"Final Answer:" convention (now tolerant of
                 markdown bolding).
  2. boxed     — the last `\\boxed{...}` in the response.
  3. last_line — the last non-empty line, as a structural fallback when
                 neither convention was followed.
  4. llm       — a judge-LLM call that reads the full response and states
                 the final answer directly, for genuinely unconventional
                 formats. Only reached if 1-3 all fail.

Every result records which strategy matched (`Extraction.strategy`), so a
silent zero-score from format drift is distinguishable from a genuine
"the agent never committed to an answer."
"""

import json
import re
from dataclasses import dataclass

from . import judge_audit

_ANSWER_LINE_RE = re.compile(r"(?im)^\s*\**\s*(?:final\s+)?answer\s*:\s*\**\s*(.+?)\s*\**\s*$")
_BOXED_RE = re.compile(r"\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")

_EXTRACT_SYSTEM_PROMPT = (
    "You extract the FINAL answer from a math solution. You are not judging "
    "correctness, only identifying what the responder's final answer was, "
    "exactly as they stated it.\n\n"
    "Respond with ONLY a JSON object, no other text:\n"
    '{"answer": "<the final answer, verbatim, or null if the response '
    'genuinely never commits to one>"}'
)


@dataclass
class Extraction:
    raw: str | None  # the extracted answer text, or None if nothing was found
    strategy: str  # "regex" | "boxed" | "last_line" | "llm" | "none"


def extract_answer_line(response: str) -> str | None:
    """Return the text after the last 'Answer:'/'Final Answer:' line, or None."""
    matches = list(_ANSWER_LINE_RE.finditer(response))
    if not matches:
        return None
    return matches[-1].group(1).strip()


def extract_boxed(response: str) -> str | None:
    """Return the contents of the last `\\boxed{...}`, or None."""
    matches = list(_BOXED_RE.finditer(response))
    if not matches:
        return None
    return matches[-1].group(1).strip()


def extract_last_nonempty_line(response: str) -> str | None:
    """Return the last non-blank line of the response, or None."""
    for line in reversed(response.strip().splitlines()):
        if line.strip():
            return line.strip()
    return None


def has_reasoning_steps(response: str) -> bool:
    """Cheap heuristic: is there substantive text before the final answer line?

    Not a substitute for the LLM step-validator (which checks whether the
    steps are actually *correct*) — this only catches the easy case of a
    bare "Answer: X" with no working shown at all, without spending an LLM
    call on it.
    """
    matches = list(_ANSWER_LINE_RE.finditer(response))
    body = response[: matches[-1].start()] if matches else response
    return len(body.split()) >= 15


def extract_single_letter(answer_line: str | None) -> str | None:
    """Extract an A-D option letter from an answer line — the *last* one
    mentioned, consistent with `extract_answer_line`'s own "most recent
    signal wins" policy (a line like "not B, the answer is C" should
    resolve to C, not B)."""
    if not answer_line:
        return None
    matches = re.findall(r"\b([A-D])\b", answer_line.upper())
    return matches[-1] if matches else None


def extract_multi_letters(answer_line: str | None) -> set[str]:
    """Extract every A-D option letter mentioned in an answer line."""
    if not answer_line:
        return set()
    return set(re.findall(r"\b([A-D])\b", answer_line.upper()))


def extract_numeric(answer_line: str | None) -> float | None:
    """Extract the *last* signed decimal number from an answer line."""
    if not answer_line:
        return None
    matches = re.findall(r"-?\d+(?:\.\d+)?", answer_line)
    return float(matches[-1]) if matches else None


def _parses_for_type(answer_type: str, text: str | None) -> bool:
    if answer_type == "single":
        return extract_single_letter(text) is not None
    if answer_type == "multi":
        return len(extract_multi_letters(text)) > 0
    if answer_type == "numeric":
        return extract_numeric(text) is not None
    raise ValueError(f"unknown answer_type {answer_type!r}")


async def _extract_via_llm(provider, question_text: str, response_text: str) -> str | None:
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question:\n{question_text}\n\nResponse:\n{response_text}"},
    ]
    try:
        completion = await provider.complete(messages)
        parsed = json.loads(completion)
        answer = parsed.get("answer") if isinstance(parsed, dict) else None
        result = str(answer).strip() if answer not in (None, "null", "") else None
        judge_audit.log("extract_answer", question_text, response_text, completion, {"answer": result})
        return result
    except Exception as e:  # noqa: BLE001 — a judge outage must degrade to "no answer found", never crash the run
        judge_audit.log("extract_answer", question_text, response_text, "", {"error": str(e)})
        return None


async def extract_answer(
    provider,
    answer_type: str,
    question_text: str,
    response_text: str,
    *,
    cache: dict | None = None,
) -> Extraction:
    """Run the regex -> boxed -> last_line -> llm cascade for one response."""
    cache_key = ("extract", answer_type, response_text)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    for strategy, extractor in (
        ("regex", extract_answer_line),
        ("boxed", extract_boxed),
        ("last_line", extract_last_nonempty_line),
    ):
        candidate = extractor(response_text)
        if candidate is not None and _parses_for_type(answer_type, candidate):
            result = Extraction(raw=candidate, strategy=strategy)
            if cache is not None:
                cache[cache_key] = result
            return result

    llm_answer = await _extract_via_llm(provider, question_text, response_text)
    result = (
        Extraction(raw=llm_answer, strategy="llm")
        if llm_answer is not None and _parses_for_type(answer_type, llm_answer)
        else Extraction(raw=None, strategy="none")
    )
    if cache is not None:
        cache[cache_key] = result
    return result

# math_eval — Gaps & Improvement Opportunities

Review of `math_eval/` as of the current codebase (8 JEE questions × 3 iterations,
retry-driven conversation loop, dual marking+judge scoring). Findings are grounded
in the actual code, not speculative — each includes the file/line and a concrete
failure scenario.

## Status

Findings 1, 2, 4, 5, 6, 7, 8, 9, 10, 12 have been implemented (see diffs in
`answer_extraction.py`, `marking.py`, `step_validator.py`, `driver.py`,
`scorer.py`, `agent_adapter.py`, `build_test_cases.py`, `iteration_stats.py`
(new), `run_eval.py`, `constants.py` (new), `judge_audit.py` (new), and
`math-solver-agent/backend/main.py`). 3 and 11 were explicitly deferred —
this is a demo project, not something carrying a real test-coverage or
question-bank obligation. Each finding below is left as-is for the
historical record; treat the numbered list as "what prompted the fix," not
as the current state of the code.

## High priority

### 1. Answer/option extraction is a single regex, with no fallback
`answer_extraction.py:11` — `_ANSWER_LINE_RE = r"(?im)^\s*answer\s*:\s*(.+)\s*$"`.
Every scoring path (`marking.py`, `driver.py`'s diagnosis, `should_continue`) is
downstream of this one pattern. If the agent under test ever deviates from the
exact `Answer: <x>` convention — `**Answer:**`, `Final Answer:`, an answer
embedded only inside `\boxed{...}` (which is how math-gpt.org's own agent formats
its output, per `API.md` in the sibling demo), or the word "answer" appearing
mid-sentence before the real answer line — extraction silently returns `None`.
That's scored identically to "the agent didn't know," even when the agent solved
the problem correctly and explained it well. There's no secondary extraction
strategy and no warning/flag when extraction fails vs. genuinely finds no answer.

**Fix:** add a fallback extractor (e.g. last `\boxed{...}`, or last non-empty
line) and record *which* strategy matched in the score reasoning, so silent
zero-scores from format drift are distinguishable from real wrong answers.

### 2. Retry idempotency guard doesn't cover the actual race it's documented against
`math-solver-agent/backend/main.py:33-50` — `_append_user_turn_idempotent` only
dedupes when the *last stored message is the same user text*. But
`math_eval/retry.py` retries on `httpx.TransportError` (which includes read
timeouts), not just failures before the server did any work. If the backend
fully completes a turn (appends user, generates, appends assistant, returns 200)
but the HTTP response is lost in transit before the eval's client times out, the
retry lands with `messages[-1]["role"] == "assistant"` — the idempotency check
doesn't match, so `_append_user_turn_idempotent` appends the *same question a
second time* and a second assistant turn is generated. The eval only sees the
second response, but the backend's server-side session (which is what actually
gets sent to the LLM as context on every subsequent turn) now silently carries a
duplicated Q&A pair for the rest of that conversation. The comment in
`agent_adapter.py:49-53` asserts this is safe; it's only safe for the
failure-before-completion case, not the lost-response-after-completion case.

**Fix:** either make the idempotency key structural (e.g. a client-generated
per-attempt request ID the backend can dedupe on) or have `_append_user_turn_idempotent`
also check "does the second-to-last message match this user turn" to catch the
post-completion race.

### 3. No project-authored tests for the eval harness itself
`find` across `demo-math-solver-agent-evalite/` turns up zero test files outside
vendored `.venv` packages. `marking.py` explicitly advertises itself as "pure and
independently testable" in its docstring, and `answer_extraction.py` is exactly
the kind of regex-heavy module that silently breaks (see #1) — but neither has
unit tests. The scoring math in `scorer.py` (weights, clamping, the
`passed = full_marks and steps_valid` rule) is also untested, so a refactor could
silently change what "pass" means without any test failing.

**Fix:** at minimum, unit-test `marking.score_answer` (all four rubric shapes +
partial-credit table) and `answer_extraction.py` against a table of real
model-output strings, including malformed ones.

## Medium priority

### 4. The step-quality judge is a single, un-audited LLM call gating `passed`
`step_validator.py` — one call to whichever provider `JUDGE_PROVIDER` selects
decides `steps_valid`, and `passed = full_marks and steps_valid`
(`scorer.py:56`). There's no self-consistency check (e.g. 2-3 judge calls with a
majority vote), no calibration sample validated against human labels, and the
raw judge completion isn't persisted anywhere — only the parsed
`steps_shown`/`steps_valid`/`explanation` survive into `case_results`. If the
judge model has any systematic bias (e.g. too strict on JEE's terse proof style,
or too lenient on hand-wavy derivations), every run's `passed` rate inherits that
bias invisibly, and there's no way to audit it after the fact since the raw
completion is gone.

**Fix:** log the raw judge completion (even just to `result_json`), and consider
running the judge 2-3× with majority vote for a more stable `steps_valid` signal.

### 5. Judge parse failure is scored as "invalid steps," not "unknown"
`step_validator.py:56-61` — any JSON parse failure from the judge (malformed
output, an unexpected shape, a truncated response) returns
`steps_shown=False, steps_valid=False`. That's indistinguishable in stored data
from the judge genuinely reviewing the response and deciding the steps were
bad — but it's really "the judge call misbehaved," which should arguably be
excluded from scoring or retried, not silently counted against the agent under
test.

**Fix:** add a distinct `judge_error: bool` field (or similar) to the score
reasoning/metadata so parse failures are auditable separately from genuine
"steps invalid" judgments.

### 6. `should_continue()` only checks answer correctness, not step validity
`driver.py:40-44` — `_diagnose()` (used by `should_continue`) calls
`score_answer` directly; it never calls the judge. So a response with a fully
correct final answer but bogus/invalid reasoning ends the conversation
immediately on turn 0 — the driver has no way to ask for better steps once the
answer itself is right. Combined with `passed = full_marks and steps_valid`,
this means an agent can reliably fail eval on step quality with *zero
opportunity to retry on that specific dimension*, only on wrong answers. That
may be intentional (retries would need to leak the "answer is right, steps
aren't" signal, which risks nudging), but it's worth confirming it's a
deliberate design choice rather than an oversight, since the driver's own
`next_message()` already has a "steps not shown" feedback branch that can
never actually fire once the answer is correct.

### 7. No cross-iteration aggregation despite `iterations=3`
`build_test_cases.py:20` runs each question 3 independent times, but nothing
downstream (`run_eval.py`, `SqliteStorage`, the `runs`/`case_results` schema)
rolls those 3 runs into a per-question mean/variance or majority-pass signal.
Each iteration's FINAL row is stored flat, distinguishable only by the
`[iter=N]` suffix baked into `case_id` (as we found earlier querying
`evalite.db` directly). Anyone wanting "how consistent is the agent on this
specific question across 3 tries" has to hand-write that aggregation query
themselves — there's no first-class support for it, even though variance across
iterations is presumably the whole reason `iterations=3` exists.

**Fix:** either a small aggregation step in `run_eval.py` after `runner.run()`,
or a `base_case_id` column so consumers don't need to parse `[iter=N]` out of a
string.

### 8. Negative marking is invisible to `Score.value`
`scorer.py:15-17` (docstring) already flags this as an accepted simplification:
`answer_fraction = clamp(points/max_points, 0, 1)` means an "unanswered" (0
points) and a confidently-wrong Section 1/2/4 answer (-1 or -2 points, JEE's
actual negative marking) score identically at `answer_fraction = 0`. If the
purpose of this eval ever extends to studying whether the agent guesses under
uncertainty vs. abstains — a meaningfully different and important behavior for
a JEE-marked exam — the current `Score.value` can't distinguish them; only the
free-text `reasoning` string can, which isn't queryable.

## Low priority / hardening

### 9. Single-match regexes can mis-extract from explanatory answer lines
`answer_extraction.py:39,47,54` — `extract_single_letter`, `extract_multi_letters`,
and `extract_numeric` all scan the *whole* answer line for the first (or all)
A–D letters / first number. A line like `Answer: not B, the answer is C` would
extract `B` as the (wrong) single letter, or `{B, C}` for multi when only `C`
was intended. This is inconsistent with `extract_answer_line`'s own policy of
taking the *last* `Answer:` match when multiple exist — the sub-extractors don't
apply the same "prefer the most recent/final signal" discipline.

### 10. Section 2's partial-credit table silently degrades for `len(correct) == 1`
`marking.py:35-39` — `_MULTI_PARTIAL_CREDIT` only has entries for
`len(correct)` in `{2, 3, 4}`. A section-2 question authored with a single
correct option (valid per JEE's own format, just not present in the current 8
questions) would hit `.get(1, {}).get(len(chosen), 0.0)` and silently score 0
partial credit in cases that might warrant more nuanced handling — there's no
assertion at question-authoring time (`questions.py`) that `answer_spec` shapes
match what `marking.py` can actually handle.

### 11. Fixed 8-question set limits statistical confidence
`questions.py` — 2 questions per section, 8 total. Combined with `iterations=3`,
that's 24 conversations per run. Any single ambiguous question or extraction bug
(see #1, #9) skews 1/8 of the total pass rate. For a "how good is this agent at
JEE math" signal this is a reasonable smoke-test size, but it's thin for
detecting small regressions between agent versions.

### 12. Tuning constants split across inconsistent configurability
`retry.py`'s `RETRY_MAX_ATTEMPTS`/`RETRY_BASE_DELAY_SECONDS` are env-var
overridable at call time; `build_test_cases.py`'s `MAX_RETRIES`/`ITERATIONS` are
hardcoded module constants. Minor inconsistency, but it means changing retry
budget or iteration count for an experiment requires an edit + redeploy rather
than an env var like everything else in this module already supports.

---

## Suggested priority order
1. Fix #1 (answer extraction fallback) — highest blast radius, silently zeroes
   otherwise-correct responses.
2. Fix #2 (idempotency race) — corrupts server-side conversation state in a way
   that's invisible to the eval itself.
3. Add tests for #1 and `marking.py` (#3) — cheapest way to catch regressions in
   the two modules everything else depends on.
4. Add judge auditability (#4, #5) — needed before trusting `passed` at scale.
5. Everything else is quality-of-life / statistical rigor, worth doing but not
   blocking.

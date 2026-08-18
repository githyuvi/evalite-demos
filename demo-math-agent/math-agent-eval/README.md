# math-agent-eval

An evalite-based evaluation suite for [math-solver-agent](../math-solver-agent),
built on **evalite as a Python package** (not the CLI/YAML flow — see
"Why Python, not YAML" below).

Test questions are two-per-section, transcribed from the official answer
key `math-solver-agent/2025_1_English.pdf` (JEE Advanced 2025, Paper 1,
Mathematics), chosen to cover every marking-scheme shape in that paper.

## Setup

```bash
cd math-agent-eval
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # editable-installs evalite from ../../../evalite
cp .env.example .env              # set JUDGE_PROVIDER + the matching API key
```

Make sure `math-solver-agent`'s backend is running first (`uvicorn main:app`
in `math-solver-agent/backend`), then:

```bash
python -m math_eval.run_eval
```

This prints a per-turn report and writes results to `evalite.db`, read by
[`math-agent-eval-ui`](../math-agent-eval-ui) to browse afterward.

## API

`api/` is a small FastAPI app that serves this project's own `evalite.db`
over HTTP — a unified backend, not a separate one: this same project both
runs the eval (`python -m math_eval.run_eval`, above) and serves its
results. (It used to be a separate app under
`math-agent-eval-ui/backend`, reaching in via a `sys.path` hack — now it's
just a sibling package importing `math_eval` directly.) This is additive;
it doesn't change the CLI usage above.

```bash
cd math-agent-eval
source .venv/bin/activate
uvicorn api.main:app --reload --port 8100
# or: python -m api.main
```

Endpoints:

- `GET /api/runs` — list recent runs with case-level pass/fail summaries.
- `POST /api/runs` — start a new eval run in the background (the same
  eval `python -m math_eval.run_eval` runs) and return immediately (202).
  Only one run at a time — a second call while one is in flight gets 409.
- `GET /api/runs/status` — status of the (at most one) in-flight or most
  recently finished run started via `POST /api/runs`: `idle` / `running` /
  `complete` / `failed`, plus `run_id`/timestamps/`error`. A full run takes
  several minutes at this eval's deliberately low concurrency, and
  `run_eval.py` prints nothing until it's done — poll this instead of
  guessing whether it's stuck.
- `GET /api/runs/{run_id}` — a run's raw `RunResult`.
- `GET /api/runs/{run_id}/detail?threshold=0.5` — overview stats + full
  per-case/per-iteration/per-turn breakdown.

`EVAL_DB_PATH` (same env var `run_eval.py` uses) overrides which db file
it reads; defaults to `math-agent-eval/evalite.db`. `EVAL_API_PORT`
overrides the port when running via `python -m api.main` (default 8100,
matching `math-agent-eval-ui/frontend`'s hardcoded `API_BASE`).

[`math-agent-eval-ui`](../math-agent-eval-ui)'s frontend is the consumer
of this API.

## Rate limits and retry/backoff

Two separate HTTP call sites can hit a transient failure — the judge LLM
call (`math_eval/llm_provider.py`) and the call into `math-solver-agent`'s
backend (`math_eval/agent_adapter.py`) — and both retry through the same
`math_eval/retry.py` helper on 429/500/502/503/504 or a connection error,
with exponential backoff + jitter. This is deliberately *not* added to
`math-solver-agent` itself: it's the system under test, so silently
retrying inside it would mask the exact failure behavior the eval is
supposed to measure.

429 (rate limiting) is the one you're most likely to hit on a free-tier
key — each conversation makes a solver call *and* a judge call per turn,
so `MAX_WORKERS` concurrency multiplies request rate quickly. Both retry
behavior and concurrency are configurable via `.env`, no code changes
needed:

```bash
MAX_WORKERS=4                 # lower this first if you're seeing 429s
RETRY_MAX_ATTEMPTS=3          # raise for a flakier/more rate-limited key
RETRY_BASE_DELAY_SECONDS=1.0  # rate limits often need tens of seconds to
                               # clear, not sub-second backoff — raise this too
```

## How scoring works

`math_eval/marking.py` transcribes JEE's own per-section marking scheme:

| Section | Type | Full marks | Partial credit | Unanswered | Wrong |
|---|---|---|---|---|---|
| 1 | single correct option | +3 | — | 0 | -1 |
| 2 | one-or-more correct options | +4 | +1 to +3, depending on how many correct options exist and how many (all-correct) were chosen | 0 | -2 |
| 3 | numerical value | +4 | — | 0 | 0 (no negative marking) |
| 4 | match-the-list, single combination | +4 | — | 0 | -1 |

Section 3's two questions deliberately include one **exact** answer (105)
and one **accepted range** ([1.15, 1.25]) — JEE itself scores numerical
answers by range when the true answer isn't a clean integer, so the
scorer's numeric check supports both.

`math_eval/scorer.py` (`JEEConversationScorer`) combines two independent
signals into evalite's `Score`:

1. **Final-answer correctness** — the response's `Answer: ...` line is
   parsed and checked against the section's rubric above. This earns
   0–100% of the section's points (negative marks are clamped to 0 for
   evalite's `Score.value`, which can't go below 0 — the actual JEE point
   deduction is preserved in `Score.reasoning` instead).
2. **Steps quality** — an LLM judge (`step_validator.py`) checks whether
   the response shows genuine step-by-step working, and whether that
   working is mathematically valid and actually supports the stated final
   answer. This exists because JEE's own answer key only grades the final
   selection — an agent could land on the right option with a bogus
   derivation, or the wrong one despite mostly-sound reasoning, and a bare
   answer-key comparison can't tell those apart.

`Score.value = 0.7 * answer_correctness + 0.3 * steps_quality`.
`Score.passed` requires **both** full marks *and* valid steps, so a lucky
guess with broken reasoning doesn't read as a clean pass.

## The retry conversation

Each question runs as a `ConversationTestCase` (multi-turn), driven by
`math_eval/driver.py`'s `MathTutorDriver`:

- If the first attempt's answer is wrong, or no working was shown, the
  driver sends a **generic, fixed-template** follow-up — "your answer is
  wrong, try again" / "you didn't show your steps" — up to 2 retries.
- The driver **never reveals the correct answer or value**. Its messages
  are hardcoded templates, not LLM-generated, specifically so there's no
  path by which a "helpful" hint could leak the answer.
- Per-conversation retry count is derived from the turn history itself
  (not stored on the driver instance) — the same driver object is shared
  across all `iterations` of a question, which run concurrently, so any
  instance-mutable counter would race.

`iterations: 3` on every test case (per spec) reruns each question's whole
conversation independently three times, to see how consistent the agent
is — separate from the in-conversation retry loop above.

A custom `FinalTurnAccumulator` (not evalite's built-in averaging one)
folds each conversation's turns into a single score by keeping only the
**last** turn's result — matching real exam semantics, where only the
final submitted answer counts, not earlier wrong attempts.

## Why Python, not YAML

evalite's YAML test-set loader only covers single-turn `TestCase`/`TestSet`.
`ConversationTestCase.driver`/`.scorer` take live Python objects (see
`evalite/testcase/conversation.py`), so a multi-turn, custom-scored eval
like this one is naturally built in Python (`build_test_cases.py`) instead
of YAML.

## Files

- `math_eval/questions.py` — the 8 selected questions + ground-truth answers.
- `math_eval/answer_extraction.py` / `marking.py` — deterministic parsing +
  JEE point rubric. Pure, no I/O.
- `math_eval/step_validator.py` — LLM step-quality judge.
- `math_eval/scorer.py` — combines the two into evalite's `Score`.
- `math_eval/driver.py` — the naive, non-revealing retry conversation.
- `math_eval/accumulator.py` — final-turn-only score folding.
- `math_eval/agent_adapter.py` — wraps math-solver-agent's `/api/query`.
- `math_eval/llm_provider.py` — Gemini/DeepSeek `LLMProvider` for the judge.
- `math_eval/build_test_cases.py` / `run_eval.py` — wiring + entry point.
- `api/main.py` / `api/aggregation.py` — the FastAPI app (see "API" above).

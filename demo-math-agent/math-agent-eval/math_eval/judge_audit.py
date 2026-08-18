"""Append-only audit log of raw judge-LLM completions.

`step_validator.validate_steps` and `answer_extraction`'s LLM fallback only
persist their *parsed* result into `Score`/`CaseResult` — the raw completion
text is otherwise discarded, which makes it impossible to audit *why* the
judge produced a given verdict after the fact (gap #4 in
GAPS_AND_IMPROVEMENTS.md). This module writes one JSON line per judge call
to `JUDGE_AUDIT_LOG_PATH` (default `judge_audit.jsonl`) so raw completions
survive the run.

Best-effort only: a logging failure must never break the eval run itself
(same principle as `retry.py`/`agent_adapter.py` — infrastructure around
the eval shouldn't be able to take down the eval).
"""

import json
import os
import time

_PATH = os.environ.get("JUDGE_AUDIT_LOG_PATH", "judge_audit.jsonl")


def log(kind: str, question_text: str, response_text: str, raw_completion: str, parsed: dict) -> None:
    try:
        with open(_PATH, "a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "kind": kind,
                        "question": question_text[:300],
                        "response": response_text[:1000],
                        "raw_completion": raw_completion,
                        "parsed": parsed,
                    }
                )
                + "\n"
            )
    except OSError:
        pass

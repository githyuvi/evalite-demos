"""math-agent-eval's own API: read-only view over this project's SQLite
eval results (`evalite.db`), serving the math-agent-eval-ui frontend.

Formerly a separate FastAPI app under math-agent-eval-ui/backend (its own
venv, reaching into this project's `evalite.db` and `math_eval` package
via a `sys.path` hack). Moved here so this is one unified backend: the
same project that runs the eval (`python -m math_eval.run_eval`) also
serves its results over HTTP, with `math_eval` imported as a normal
sibling package.

Why not just `evalite serve`: evalite's built-in API server only
lists/shows runs it started itself via its own POST /api/v1/runs (they're
tracked in an in-memory registry, not read from storage — see
evalite/server/routes/runs.py's module docstring). Our eval runs outside
that server (a plain script using ConversationRunner, a custom scorer, and
a custom driver — none of which the server's REST trigger supports, which
is hardcoded to a single-turn Runner + DefaultScorer). So a run saved via
`SqliteStorage.save_run()` from run_eval.py would never show up through
`evalite serve`'s API. This app instead calls `SqliteStorage.list_runs()`
/ `.get_run()` directly — the same Protocol methods, just read outside
that server process.

Run it:
    cd math-agent-eval
    source .venv/bin/activate
    uvicorn api.main:app --reload --port 8100
or:
    python -m api.main
"""

import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from evalite.storage.sqlite import SqliteStorage
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.aggregation import build_case_detail, build_case_pass_summary, build_overview
from math_eval.run_eval import run_and_save

load_dotenv()

# api/main.py -> parents[1] is math-agent-eval/, same dir run_eval.py's
# default "evalite.db" resolves against when run from cwd math-agent-eval.
# EVAL_API_PORT var name kept consistent with run_eval.py's existing
# EVAL_DB_PATH usage.
DEFAULT_DB_PATH = str(Path(__file__).resolve().parents[1] / "evalite.db")
DB_PATH = os.environ.get("EVAL_DB_PATH", DEFAULT_DB_PATH)

app = FastAPI(title="math-agent-eval")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = SqliteStorage(db_path=DB_PATH)

# Server-process-lifetime state for the one eval run this process will run
# at a time — not persisted to `evalite.db`, since it's about "is a run in
# flight right now," not a completed run's results. asyncio.create_task
# only holds a *weak* reference to the task it returns, so `_background_tasks`
# retains a strong one until the task finishes (same pitfall/fix as
# evalite/server/routes/runs.py's start_run).
_background_tasks: set[asyncio.Task] = set()
_run_state: dict = {
    "status": "idle",  # idle | running | complete | failed
    "run_id": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


@app.on_event("startup")
async def on_startup() -> None:
    # Idempotent (CREATE TABLE IF NOT EXISTS semantics) — needed so this
    # app doesn't 500 on a fresh checkout where run_eval.py hasn't run yet
    # and evalite.db doesn't exist. Safe to call even when run_eval.py
    # already created the schema.
    await storage.init()


@app.get("/api/runs")
async def list_runs(limit: int = 20):
    """List recent runs, each enriched with case-level (not per-turn,
    not per-iteration) pass/fail counts.

    `storage.list_runs()` alone returns evalite's raw `passed`/`failed`
    columns, which count every `CaseResult` row (every turn attempt and
    every FINAL row across all iterations) — for 8 questions x 3
    iterations that's dozens of rows, not 8, which reads as nonsensical
    next to the per-case detail view. Recomputing this per run means an
    extra `get_run` fetch per row, which is fine at this app's scale (a
    handful of local eval runs, not a production dashboard).
    """
    runs = await storage.list_runs(limit=limit)
    enriched = []
    for run_row in runs:
        full_run = await storage.get_run(run_row["run_id"])
        case_summary = build_case_pass_summary(full_run.case_results) if full_run else None
        enriched.append({**run_row, "case_summary": case_summary})
    return enriched


async def _execute_run() -> None:
    """Background task: run the eval and update `_run_state`.

    Never raises — an unhandled exception inside a background asyncio task
    has no caller to propagate to and is silently swallowed, so any
    failure (bad backend response, judge API error) is caught and recorded
    on `_run_state` instead (same reasoning as
    evalite/server/routes/runs.py's `_execute_run`).
    """
    try:
        run_id, _result = await run_and_save(storage)
        _run_state["status"] = "complete"
        _run_state["run_id"] = run_id
        _run_state["finished_at"] = time.time()
    except Exception as e:
        _run_state["status"] = "failed"
        _run_state["error"] = str(e)
        _run_state["finished_at"] = time.time()


@app.post("/api/runs", status_code=202)
async def trigger_run():
    """Start a new eval run in the background and return immediately.

    Only one run at a time: this eval is deliberately low-concurrency
    against a rate-limited judge LLM (see `MAX_WORKERS`/`RETRY_*` in
    `.env`), so two runs at once would only make that worse, and they'd
    both be writing to the same `evalite.db`. A run in flight takes
    several minutes — poll `GET /api/runs/status` for progress instead of
    waiting on this request, which returns as soon as the run has started,
    not once it's done.
    """
    if _run_state["status"] == "running":
        raise HTTPException(status_code=409, detail="A run is already in progress")

    _run_state.update(
        status="running", run_id=None, started_at=time.time(), finished_at=None, error=None
    )

    task = asyncio.create_task(_execute_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"status": "started"}


@app.get("/api/runs/status")
async def run_status():
    """Current state of the (at most one) in-flight or most recently
    finished run started via `POST /api/runs`. `run_eval.py`'s own report
    only prints once the whole run completes, so without this there's no
    way to tell a slow run from a stuck one from outside the process.

    Registered before `GET /api/runs/{run_id}` so `/status` isn't matched
    as a `run_id` path param — FastAPI resolves routes in registration
    order for same-shaped paths.
    """
    return _run_state


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = await storage.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.model_dump()


@app.get("/api/runs/{run_id}/detail")
async def get_run_detail(run_id: str, threshold: float = 0.5):
    """Overview stats + per-case, per-iteration, per-turn breakdown for one
    run — what the frontend's overview panel and case accordions render.

    `threshold` buckets each (question, iteration) conversation's FINAL
    score into above/below, separately from system failures and from
    evalite's own stricter `passed` (full marks AND valid steps) — a
    softer "was this at least decent" signal, not a duplicate of pass/fail.
    """
    run = await storage.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "test_set_name": run.test_set_name,
        # `total`/`passed`/`failed` below are evalite's own row-level counts
        # (every turn attempt + every FINAL row, across all iterations) —
        # kept for reference, but `case_summary` is the case-level count
        # (one entry per question) the frontend should actually display.
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "pass_rate": run.pass_rate,
        "case_summary": build_case_pass_summary(run.case_results),
        "overview": build_overview(run.case_results, threshold),
        "cases": build_case_detail(run.case_results),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("EVAL_API_PORT", "8100")),
        reload=False,
    )

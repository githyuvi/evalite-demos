"""Entry point: run the JEE math eval against math-solver-agent and persist
results to SQLite (read by math-agent-eval-ui).

Usage:
    cd math-agent-eval
    source venv/bin/activate
    python -m math_eval.run_eval
"""

import asyncio
import os

from dotenv import load_dotenv
from evalite import ConversationRunner, RunResult
from evalite.storage.sqlite import SqliteStorage

from .agent_adapter import MathSolverDemoAdapter
from .build_test_cases import build_test_cases
from .iteration_stats import (
    build_case_series,
    overall_average_score,
    per_iteration_averages,
    per_iteration_failure_counts,
)
from .llm_provider import get_judge_provider

load_dotenv()


async def run_and_save(storage: SqliteStorage) -> tuple[str, RunResult]:
    """Build the test cases, run them against math-solver-agent, and persist
    the result via `storage`. Returns `(run_id, result)`.

    Factored out of `main()` so `api/main.py`'s `POST /api/runs` can trigger
    the exact same eval this CLI entry point runs, without duplicating the
    provider/adapter/runner wiring.
    """
    provider = get_judge_provider()
    cases = build_test_cases(provider)

    adapter = MathSolverDemoAdapter(base_url=os.environ.get("MATH_AGENT_URL", "http://localhost:8000"))
    runner = ConversationRunner(adapter=adapter, max_workers=int(os.environ.get("MAX_WORKERS", "4")))

    try:
        result = await runner.run("jee_2025_paper1_math_sample", cases)
    finally:
        await adapter.aclose()

    run_id = await storage.save_run(result)
    return run_id, result


async def main() -> None:
    storage = SqliteStorage(db_path=os.environ.get("EVAL_DB_PATH", "evalite.db"))
    await storage.init()

    run_id, result = await run_and_save(storage)

    print(f"\nRun saved as {run_id}")
    print(
        f"Total rows: {result.total}  Passed: {result.passed}  "
        f"Failed: {result.failed}  Pass rate: {result.pass_rate:.1%}"
    )
    print()
    for cr in sorted(result.case_results, key=lambda c: (c.case_id, c.iteration)):
        turn_label = "FINAL" if cr.iteration == -1 else f"turn {cr.iteration}"
        marker = "PASS" if cr.passed else "FAIL"
        print(f"[{marker}] {cr.case_id:<28} {turn_label:<9} score={cr.score.value:.2f}  {cr.score.reasoning}")

    series = build_case_series(result.case_results)
    iter_avgs = per_iteration_averages(series)
    fail_counts = per_iteration_failure_counts(series)
    overall = overall_average_score(series)

    print("\nPer-iteration average score (simulating repeated user queries):")
    for i in sorted(iter_avgs):
        fails = fail_counts.get(i, 0)
        fail_note = f"  ({fails} system failure(s) excluded)" if fails else ""
        print(f"  iter {i + 1}: {iter_avgs[i]:.3f}{fail_note}")

    if overall is not None:
        print(
            f"\nOverall average score (each case's last iteration, "
            f"excluding cases with any system failure): {overall:.3f}"
        )
    else:
        print("\nOverall average score: n/a (every case hit a system failure)")


if __name__ == "__main__":
    asyncio.run(main())

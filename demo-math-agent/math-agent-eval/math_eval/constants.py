"""Shared sentinel strings used across math_eval.

`SYSTEM_FAILURE_PREFIX` marks an `AgentResponse.content` / `Score.reasoning`
as representing an infrastructure failure (backend request exhausted its
retries, judge provider call failed) rather than a genuine agent response.
evalite's `Score`/`CaseResult` models have no field for this distinction
(and adding one would mean forking evalite), so it's encoded as a prefix
convention instead — greppable in `case_results.actual` /
`case_results.score_reasoning`, and read back by `iteration_stats.py` to
exclude failed conversations from quality aggregates without conflating
them with genuine low scores.
"""

SYSTEM_FAILURE_PREFIX = "[SYSTEM_FAILURE]"

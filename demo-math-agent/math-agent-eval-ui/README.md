# math-agent-eval-ui

A minimal read-only viewer for [math-agent-eval](../math-agent-eval)'s
results, stored in `math-agent-eval/evalite.db`. Just the frontend now —
the backend API used to live here as a separate FastAPI app/venv
(`backend/`), but has moved into `math-agent-eval` itself, so there's one
unified backend that both runs the eval and serves its results, instead
of a separate app per project. See
[`math-agent-eval/README.md`](../math-agent-eval/README.md#api) for how
to run it.

Not `evalite serve` on its own: that API only shows runs it started
itself (it reads from an in-memory registry populated by its own
`POST /api/v1/runs`, which is hardcoded to a single-turn `Runner` +
`DefaultScorer`, not the `ConversationRunner` + custom scorer this eval
uses) — see `math-agent-eval/api/main.py`'s docstring for the full
explanation. That app reads the same `SqliteStorage` directly instead.
This directory is just the plain HTML/JS frontend (same no-build-step
pattern as `math-solver-agent/frontend`).

## Run it

```bash
cd ../math-agent-eval
source .venv/bin/activate
uvicorn api.main:app --reload --port 8100
```

Then open `index.html` in a browser (or serve it:
`python -m http.server 5600`). It talks to
`http://localhost:8100` (see `API_BASE` in `app.js`).

Click a run to see its per-case, per-turn breakdown: pass/fail, score,
scorer reasoning (JEE marking explanation + steps-quality judgment), and
the agent's actual response — hover a truncated cell for the full text.

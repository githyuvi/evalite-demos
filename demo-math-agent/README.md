# math-solver-agent-evalite-demo-app

A self-contained demo: a math/physics chatbot agent, an [evalite](../../evalite)
evaluation suite built against it, and a viewer for the results. Three
pieces, one folder:

```
math-solver-agent/     the agent under test — FastAPI backend + plain HTML/JS frontend
math-agent-eval/        evalite-based eval suite (Python, not YAML) that scores it
math-agent-eval-ui/     read-only viewer for the eval's results
```

## How the pieces fit together

```
math-solver-agent/backend  <---HTTP--->  math-agent-eval/math_eval
   (the agent under test)                 (Runner + custom Scorer + Driver)
                                                    |
                                                    v
                                          math-agent-eval/evalite.db
                                                    |
                                                    v
                                          math-agent-eval/api  --->  math-agent-eval-ui
                                       (reads the same SQLite file)
```

`math-agent-eval` wraps `math-solver-agent`'s `/api/query` endpoint as an
evalite `AgentAdapter` and runs it through 8 questions transcribed from a
real JEE (Advanced) 2025 answer key — two per section, chosen to exercise
every marking-scheme shape in that paper (single-correct, multi-correct
with partial credit, exact numeric, range-accepted numeric, and
match-the-list). See `math-agent-eval/README.md` for the full scoring
design (section-aware marking + an LLM-judged steps-quality check) and the
retry-without-revealing-the-answer conversation flow.

`math-agent-eval`'s own API (`math-agent-eval/api`) — which
`math-agent-eval-ui` talks to — doesn't use evalite's own
built-in `serve` command either: that server only shows runs it started
itself through its own REST trigger, which is hardcoded to a single-turn
`Runner` + `DefaultScorer` and can't run this suite's `ConversationRunner`
+ custom scorer/driver. It reads the same `evalite.db` SQLite file
directly instead. See `math-agent-eval/api/main.py`'s docstring for the
full reasoning. This is a unified backend: the same project runs the eval
*and* serves its results, rather than a separate app per project.

## Running it end to end

```bash
# 1. Start the agent under test
cd math-solver-agent/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY / DEEPSEEK_API_KEY
uvicorn main:app --port 8000

# 2. Serve the results API (separate terminal)
cd math-agent-eval
source .venv/bin/activate
uvicorn api.main:app --port 8100
# open math-agent-eval-ui/index.html in a browser
```

Each subfolder has its own README with the details specific to that piece.

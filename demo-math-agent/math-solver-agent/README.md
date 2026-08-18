# math-solver-agent

A deliberately minimal math/physics chatbot: FastAPI backend, plain HTML/JS
frontend, JSON-file session storage. Not for production — it exists to be an
eval target for [evalite](../../../evalite), wrapped via a `send()`-shaped
`AgentAdapter`.

## Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set LLM_PROVIDER + the matching API key
uvicorn main:app --reload
```

### Switching models

`backend/providers/` has one module per provider (`gemini.py`, `deepseek.py`),
both satisfying the same `LLMProvider` protocol in `providers/base.py`
(`generate` / `generate_stream`, taking the same `[{"role", "content"}, ...]`
message list). `providers/get_provider()` picks one at request time based on
the `LLM_PROVIDER` env var — restart the server (or just flip the env var
and restart) to switch between Gemini and DeepSeek, no code changes needed.

To add another provider: drop a new module in `providers/` implementing the
same two methods, and register it in `_PROVIDERS` in `providers/__init__.py`.

Two endpoints, both taking `{"message": str, "conversation_id": str | null}`:

- `POST /api/query` — one request, one full response.
- `POST /api/stream` — one request, response streamed back as SSE (`start`,
  message chunks, `done`). Each event's `data:` line is JSON-encoded so
  multi-line step-by-step solutions don't break the stream framing.

If `conversation_id` is omitted, one is generated and returned — the caller
is expected to persist and resend it to continue the conversation. Sessions
are stored as `backend/sessions/<conversation_id>.json`, one file per
conversation, holding the full message history.

## Frontend

No build step. Just open `frontend/index.html` directly in a browser, or
serve it:

```bash
cd frontend
python -m http.server 5500
```

It talks to `http://localhost:8000` (see `API_BASE` in `app.js`) and keeps
`conversation_id` in `localStorage` so a page reload continues the same
conversation.

## Wiring this into evalite

An `AgentAdapter.send(messages)` implementation just needs to POST to
`/api/query`, passing the last stored `conversation_id`, and return the
`message.content` field as `AgentResponse.content`. Since you know the
correct answers to your own test cases, score with `RegexScorer` /
`DefaultScorer` against the `Answer:` line rather than an LLM judge.

Because the model is swappable via `LLM_PROVIDER`, the same test set can be
run twice — once per provider — to compare Gemini vs. DeepSeek on identical
math/physics cases.

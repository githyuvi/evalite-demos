"""math-solver-agent backend — two endpoints over a JSON-file conversation store.

POST /api/query  -> single request, full response
POST /api/stream -> single request, response streamed via SSE
"""

import json
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import storage
from providers import get_provider

app = FastAPI(title="math-solver-agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    message: str
    conversation_id: str | None = None


def _append_user_turn_idempotent(conversation_id: str, message: str) -> tuple[dict, str | None]:
    """Append a user turn, unless it's a retry of the most recent one.

    Callers (e.g. math-agent-eval's adapter) may retry a request with the
    same conversation_id + message after a prior attempt failed. Two
    failure points need distinct handling:

    1. The prior attempt failed *before* generating a reply — the user turn
       from that attempt was already appended, so `messages[-1]` is that
       same user message. Re-appending would duplicate it; the caller
       should proceed to generate the (first) real reply as normal.
    2. The prior attempt actually completed (user + assistant both
       appended, 200 returned) but the *response* was lost in transit
       (e.g. a client-side read timeout after the server had already
       finished), so `messages[-1]` is now the assistant reply, not the
       user message. Appending the question again *and* generating a
       second reply would silently duplicate that Q&A pair in the
       server-side history every subsequent turn's LLM call sends as
       context — worse than case 1, because it's invisible to the caller
       (who only ever sees the newest response) and compounds silently for
       the rest of the conversation. The already-stored reply from the
       first, successful attempt is what should be returned instead of
       generating a new one.

    Both are the same underlying situation — a retry of the *last user
    turn* — so we check for it at whichever position it actually landed:
    either as `messages[-1]` (case 1) or paired with the assistant reply
    that immediately followed it, i.e. `messages[-2]` (case 2).

    Returns (session, cached_reply): `cached_reply` is the already-stored
    assistant content when this is a case-2 retry, and `None` otherwise —
    callers must check it and skip generation when it's set.
    """
    session = storage.load_session(conversation_id)
    messages = session["messages"]

    def _matches_user_turn(msg: dict | None) -> bool:
        return bool(msg) and msg["role"] == "user" and msg["content"] == message

    if _matches_user_turn(messages[-1] if messages else None):
        return session, None

    if len(messages) >= 2 and messages[-1]["role"] == "assistant" and _matches_user_turn(messages[-2]):
        return session, messages[-1]["content"]

    return storage.append_message(conversation_id, "user", message), None


@app.post("/api/query")
async def query(req: QueryRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    session, cached_reply = _append_user_turn_idempotent(conversation_id, req.message)
    if cached_reply is not None:
        return {
            "conversation_id": conversation_id,
            "message": {"role": "assistant", "content": cached_reply},
        }
    reply = await get_provider().generate(session["messages"])
    storage.append_message(conversation_id, "assistant", reply)
    return {
        "conversation_id": conversation_id,
        "message": {"role": "assistant", "content": reply},
    }


@app.post("/api/stream")
async def stream(req: QueryRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    session, cached_reply = _append_user_turn_idempotent(conversation_id, req.message)
    provider = get_provider()

    async def event_generator():
        yield f"event: start\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"
        if cached_reply is not None:
            yield f"data: {json.dumps({'text': cached_reply})}\n\n"
            yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"
            return
        full_text = ""
        async for chunk in provider.generate_stream(session["messages"]):
            full_text += chunk
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        storage.append_message(conversation_id, "assistant", full_text)
        yield f"event: done\ndata: {json.dumps({'conversation_id': conversation_id})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

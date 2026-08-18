"""Flat-file JSON session storage. One file per conversation_id."""

import json
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(__file__).parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


def _path(conversation_id: str) -> Path:
    return SESSIONS_DIR / f"{conversation_id}.json"


def load_session(conversation_id: str) -> dict:
    path = _path(conversation_id)
    if not path.exists():
        return {
            "conversation_id": conversation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": [],
        }
    return json.loads(path.read_text())


def save_session(session: dict) -> None:
    _path(session["conversation_id"]).write_text(json.dumps(session, indent=2))


def append_message(conversation_id: str, role: str, content: str) -> dict:
    session = load_session(conversation_id)
    session["messages"].append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_session(session)
    return session

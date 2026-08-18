import json
import os

import httpx

from .base import SYSTEM_PROMPT


class GeminiProvider:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (see .env.example)")

    def _contents(self, messages: list[dict]) -> list[dict]:
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        return contents

    async def generate(self, messages: list[dict]) -> str:
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": self._contents(messages),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def generate_stream(self, messages: list[dict]):
        url = f"{self.base_url}/{self.model}:streamGenerateContent?alt=sse&key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": self._contents(messages),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = json.loads(line[len("data:") :].strip())
                    try:
                        text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError):
                        continue
                    yield text

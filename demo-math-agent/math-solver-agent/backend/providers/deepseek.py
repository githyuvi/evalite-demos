import json
import os

import httpx

from .base import SYSTEM_PROMPT


class DeepSeekProvider:
    """DeepSeek's API is OpenAI-compatible chat completions."""

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.base_url = "https://api.deepseek.com"
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set (see .env.example)")

    def _messages(self, messages: list[dict]) -> list[dict]:
        return [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]

    async def generate(self, messages: list[dict]) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": self._messages(messages),
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def generate_stream(self, messages: list[dict]):
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": self._messages(messages),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:") :].strip()
                    if raw == "[DONE]":
                        break
                    chunk = json.loads(raw)
                    text = chunk["choices"][0].get("delta", {}).get("content")
                    if text:
                        yield text

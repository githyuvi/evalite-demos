"""Generic evalite LLMProvider implementations (system/user/assistant
messages -> completion text) for Gemini and DeepSeek.

Deliberately NOT reusing math-solver-agent/backend/providers/{gemini,deepseek}.py:
those are built around one fixed system prompt baked into the module, with
Gemini's system_instruction handling hardcoded around it. The step-validator
judge here needs to send its own, different system prompt on every call, so
these providers handle an arbitrary system/user/assistant list generically
instead.
"""

import os

import httpx

from .retry import with_retry


class GeminiLLMProvider:
    """LLMProvider backed by Gemini's REST API."""

    def __init__(self) -> None:
        self.api_key = os.environ["GEMINI_API_KEY"]
        self.model = os.environ.get("JUDGE_GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    async def complete(self, messages: list[dict], **kwargs) -> str:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload: dict = {"contents": contents}
        if system_parts:
            payload["system_instruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"

        async def _do_request() -> dict:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()

        data = await with_retry(_do_request)
        return data["candidates"][0]["content"]["parts"][0]["text"]


class DeepSeekLLMProvider:
    """LLMProvider backed by DeepSeek's OpenAI-compatible chat completions API."""

    def __init__(self) -> None:
        self.api_key = os.environ["DEEPSEEK_API_KEY"]
        self.model = os.environ.get("JUDGE_DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.base_url = "https://api.deepseek.com"

    async def complete(self, messages: list[dict], **kwargs) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "stream": False}

        async def _do_request() -> dict:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                return resp.json()

        data = await with_retry(_do_request)
        return data["choices"][0]["message"]["content"]


def get_judge_provider():
    """Build the configured judge LLMProvider from JUDGE_PROVIDER env var."""
    name = os.environ.get("JUDGE_PROVIDER", "gemini").lower()
    if name == "gemini":
        return GeminiLLMProvider()
    if name == "deepseek":
        return DeepSeekLLMProvider()
    raise RuntimeError(f"Unknown JUDGE_PROVIDER '{name}' — choose gemini or deepseek")

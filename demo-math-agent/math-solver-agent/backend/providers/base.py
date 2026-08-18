"""Structural contract every provider module must satisfy — same
adapter-not-inheritance idea evalite uses for AgentAdapter/LLMProvider."""

from typing import AsyncIterator, Protocol

SYSTEM_PROMPT = (
    "You are a helpful math and physics tutor. Solve the problem step by "
    "step, then give a clear final answer on its own line prefixed with "
    "'Answer:'."
)


class LLMProvider(Protocol):
    async def generate(self, messages: list[dict]) -> str:
        """Return the full response text for a chat history."""
        ...

    def generate_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield response text incrementally for a chat history."""
        ...

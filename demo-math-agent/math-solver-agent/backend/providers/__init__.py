"""Provider factory — set LLM_PROVIDER=gemini|deepseek in .env to switch."""

import os

from dotenv import load_dotenv

from .base import LLMProvider
from .deepseek import DeepSeekProvider
from .gemini import GeminiProvider

load_dotenv()

_PROVIDERS = {
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider() -> LLMProvider:
    name = os.environ.get("LLM_PROVIDER", "gemini").lower()
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{name}'. Choose one of: {', '.join(_PROVIDERS)}"
        )
    return provider_cls()

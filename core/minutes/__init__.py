"""Fábrica de provedores de ata. Escolha via config: claude | openai | gemini | ollama."""
from __future__ import annotations

from core.config import MinutesConfig
from core.minutes.base import MinutesProvider


def get_provider(cfg: MinutesConfig) -> MinutesProvider:
    name = cfg.provider.lower()
    opts = cfg.options()

    # Imports lazy: mesmo com tudo instalado, só carregamos a lib do provedor ativo.
    if name == "claude":
        from core.minutes.claude import ClaudeProvider
        return ClaudeProvider(**opts)
    if name == "openai":
        from core.minutes.openai import OpenAIProvider
        return OpenAIProvider(**opts)
    if name == "gemini":
        from core.minutes.gemini import GeminiProvider
        return GeminiProvider(**opts)
    if name == "ollama":
        from core.minutes.ollama import OllamaProvider
        return OllamaProvider(**opts)

    raise ValueError(
        f"Provedor de ata desconhecido: {name!r}. "
        "Use claude, openai, gemini ou ollama."
    )

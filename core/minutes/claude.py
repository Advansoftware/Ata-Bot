"""Geração da ata via API da Claude (Anthropic)."""
from __future__ import annotations

import anthropic

from core.minutes.base import MinutesProvider


class ClaudeProvider(MinutesProvider):
    def __init__(self, model: str = "claude-opus-4-8", api_key: str = "", **_ignored):
        if not api_key.strip():
            raise RuntimeError("Chave da API da Claude (Anthropic) não configurada.")
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8000) -> str:
        # Streaming: transcrições/atas podem ser longas — evita timeout de request.
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            message = stream.get_final_message()

        parts = [b.text for b in message.content if b.type == "text"]
        return "".join(parts).strip()

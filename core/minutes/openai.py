"""Geração da ata via API da OpenAI (ChatGPT)."""
from __future__ import annotations

from openai import OpenAI

from core.minutes.base import MinutesProvider


class OpenAIProvider(MinutesProvider):
    def __init__(self, model: str = "gpt-4o-mini", api_key: str = "", **_ignored):
        if not api_key.strip():
            raise RuntimeError("Chave da API da OpenAI não configurada.")
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8000) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

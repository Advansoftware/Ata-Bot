"""Geração da ata via API do Google Gemini."""
from __future__ import annotations

from google import genai
from google.genai import types

from core.minutes.base import MinutesProvider


class GeminiProvider(MinutesProvider):
    def __init__(self, model: str = "gemini-2.0-flash", api_key: str = "", **_ignored):
        if not api_key.strip():
            raise RuntimeError("Chave da API do Gemini não configurada.")
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8000) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return (resp.text or "").strip()

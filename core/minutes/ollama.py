"""Geração da ata via Ollama (LLM 100% local — custo zero, nada sai da máquina)."""
from __future__ import annotations

import httpx

from core.minutes.base import MinutesProvider


class OllamaProvider(MinutesProvider):
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.1:8b", **_ignored):
        self.host = host.rstrip("/")
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8000) -> str:
        resp = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=600,  # LLM local pode ser lento
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

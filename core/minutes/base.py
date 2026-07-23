"""Interface comum a todos os provedores de ata + o prompt compartilhado."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MeetingMeta:
    started_at: str
    ended_at: str | None
    participants: list[str]
    language: str = "pt"


SYSTEM_PROMPT = (
    "Você é um secretário executivo que redige atas de reunião claras e objetivas "
    "a partir de transcrições. Escreva em português do Brasil, em Markdown."
)


def build_user_prompt(transcript: str, meta: MeetingMeta) -> str:
    participantes = ", ".join(meta.participants) if meta.participants else "não identificados"
    return f"""\
Gere a **ata** desta reunião a partir da transcrição abaixo.

Metadados:
- Início: {meta.started_at}
- Fim: {meta.ended_at or "—"}
- Participantes: {participantes}

Estruture a ata exatamente com estas seções (omita uma seção só se não houver conteúdo):

## Resumo
(3–5 linhas com o essencial)

## Tópicos discutidos
(bullets)

## Decisões
(bullets; se não houve, escreva "Nenhuma decisão registrada")

## Itens de ação
(bullets no formato: responsável — tarefa — prazo, quando houver)

## Pendências / próximos passos
(bullets)

Seja fiel à transcrição; não invente informações. Se algo estiver ambíguo, sinalize.

---
TRANSCRIÇÃO:
{transcript}
"""


class MinutesProvider(ABC):
    """Recebe a transcrição e devolve a ata em Markdown."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 8000) -> str:
        """Uma chamada genérica ao LLM (usada pela ata e pela condensação)."""
        ...

    def generate(self, transcript: str, meta: MeetingMeta) -> str:
        return self.complete(SYSTEM_PROMPT, build_user_prompt(transcript, meta))

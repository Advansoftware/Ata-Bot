"""Condensa transcrições longas antes de mandar para a IA gerar a ata.

Problema: uma reunião longa vira uma transcrição enorme. Mandar tudo de uma vez
pode:
  - estourar o limite de contexto do modelo (a IA nem responde), ou
  - ficar caro / lento.
Mas cortar no meio perde informação e a ata sai incompleta.

Solução (map-reduce): se a transcrição couber no orçamento, mandamos inteira
(melhor qualidade). Se não couber, dividimos em blocos que cabem, pedimos à
PRÓPRIA IA um resumo fiel de cada bloco (preservando decisões, itens de ação,
quem falou e números) e juntamos os resumos. Se ainda ficar grande, repetimos.
Assim nada é descartado — cada trecho é representado — e o texto final cabe.
"""
from __future__ import annotations

from typing import Callable, Optional

# Orçamentos em caracteres (~4 chars por token). Conservador de propósito para
# funcionar até em modelos locais com contexto pequeno (ex.: 8k tokens no Ollama).
MAX_DIRECT_CHARS = 24_000   # abaixo disto: manda a transcrição inteira
CHUNK_CHARS = 15_000        # tamanho de cada bloco condensado por vez
_MAX_ROUNDS = 4             # trava de segurança contra loop infinito

Logger = Callable[[str], None]

_CONDENSE_SYSTEM = (
    "Você condensa TRECHOS de transcrições de reunião para uso posterior numa ata. "
    "Seja fiel: não invente nada. Responda em português do Brasil."
)


def _condense_prompt(chunk: str) -> str:
    return f"""\
Abaixo está um TRECHO (parcial) da transcrição de uma reunião. Resuma-o de forma
compacta porém completa, preservando:
- tópicos discutidos;
- decisões tomadas;
- itens de ação (responsável — tarefa — prazo, quando houver);
- pendências / próximos passos;
- nomes de pessoas, números, datas e valores citados.

Use bullets curtos. NÃO escreva título nem conclusão — isto é só um trecho, será
combinado com outros depois.

TRECHO:
{chunk}
"""


def est_tokens(text: str) -> int:
    return len(text) // 4


def _split_by_lines(text: str, max_chars: int) -> list[str]:
    """Divide o texto em blocos de até max_chars, sempre em quebras de linha."""
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        # Linha única gigante: quebra na marra.
        if len(line) > max_chars:
            if cur:
                chunks.append("".join(cur))
                cur, size = [], 0
            for i in range(0, len(line), max_chars):
                chunks.append(line[i : i + max_chars])
            continue
        if size + len(line) > max_chars and cur:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line)
    if cur:
        chunks.append("".join(cur))
    return chunks


def condense_if_needed(
    transcript: str,
    provider,  # MinutesProvider (evita import circular)
    log: Optional[Logger] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Devolve um texto que cabe no orçamento para a IA gerar a ata.

    on_progress(feito, total): chamado a cada bloco condensado (para a UI mostrar
    'condensando trecho 2/5').
    """
    log = log or (lambda _m: None)
    text = transcript

    if len(text) <= MAX_DIRECT_CHARS:
        return text  # cabe direto — melhor qualidade, sem intermediário

    for _round in range(_MAX_ROUNDS):
        chunks = _split_by_lines(text, CHUNK_CHARS)
        log(
            f"Transcrição longa (~{est_tokens(text)} tokens): condensando em "
            f"{len(chunks)} trecho(s) para não estourar o contexto da IA."
        )
        notes: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(i, len(chunks))
            log(f"Condensando trecho {i}/{len(chunks)}...")
            notes.append(provider.complete(_CONDENSE_SYSTEM, _condense_prompt(chunk)))
        combined = "\n\n".join(notes)

        if len(combined) <= MAX_DIRECT_CHARS:
            return combined
        if len(combined) >= len(text):
            # Não encolheu: evita loop; corta no orçamento como último recurso.
            return combined[:MAX_DIRECT_CHARS]
        text = combined  # ainda grande: condensa de novo os resumos

    return text[:MAX_DIRECT_CHARS]

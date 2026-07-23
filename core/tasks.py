"""Itens de ação consolidados a partir das atas + estado de 'concluído'.

Cada ata (minutes.md) tem uma seção "## Itens de ação". Aqui extraímos esses
itens de todas as reuniões e guardamos o estado de concluído num JSON simples em
DATA_DIR/tasks_state.json (chave = hash estável de reunião+texto).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading

from core.config import DATA_DIR

_STATE_PATH = DATA_DIR / "tasks_state.json"
_LOCK = threading.Lock()

# Frases que a IA usa quando não há itens — não viram tarefa.
_EMPTY_HINTS = ("nenhum item", "nenhuma tarefa", "não há itens", "sem itens", "n/a")


def task_id(meeting_id: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha1(f"{meeting_id}|{norm}".encode()).hexdigest()[:12]


def parse_action_items(minutes_md: str) -> list[str]:
    """Extrai os bullets da seção '## Itens de ação' da ata."""
    if not minutes_md:
        return []
    lines = minutes_md.splitlines()
    items: list[str] = []
    in_section = False
    for line in lines:
        s = line.strip()
        if s.startswith("##"):
            # entra só na seção "Itens de ação" (tolerante a acento/variação)
            low = s.lower()
            in_section = "iten" in low and ("aç" in low or "ac" in low)
            continue
        if not in_section:
            continue
        m = re.match(r"^[-*+]\s+(.*)$", s)
        if not m:
            continue
        text = m.group(1).strip().lstrip("*").strip()
        if not text:
            continue
        if any(h in text.lower() for h in _EMPTY_HINTS):
            continue
        items.append(text)
    return items


def load_state() -> dict:
    with _LOCK:
        if not _STATE_PATH.exists():
            return {}
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}


def set_done(tid: str, done: bool) -> None:
    with _LOCK:
        state = {}
        if _STATE_PATH.exists():
            try:
                state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                state = {}
        if done:
            state[tid] = True
        else:
            state.pop(tid, None)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

"""Sessões do chat global — conversas separadas, persistidas e apagáveis.

Guardadas num único JSON em DATA_DIR/chat_sessions.json. Cada sessão tem um id,
um título (derivado da 1ª pergunta), timestamps e a lista de mensagens
({role: 'user'|'assistant', content}).
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from core.config import DATA_DIR

_PATH = DATA_DIR / "chat_sessions.json"
_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load() -> dict:
    if not _PATH.exists():
        return {"sessions": []}
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sessions"), list):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"sessions": []}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary(s: dict) -> dict:
    return {
        "id": s["id"],
        "title": s.get("title") or "Nova conversa",
        "updated_at": s.get("updated_at", ""),
        "count": len(s.get("messages", [])),
    }


def list_sessions() -> list[dict]:
    data = _load()
    ordered = sorted(data["sessions"], key=lambda x: x.get("updated_at", ""), reverse=True)
    return [_summary(s) for s in ordered]


def get_session(sid: str) -> dict | None:
    for s in _load()["sessions"]:
        if s["id"] == sid:
            return s
    return None


def create_session() -> dict:
    with _LOCK:
        data = _load()
        s = {
            "id": uuid.uuid4().hex[:12],
            "title": "",
            "created_at": _now(),
            "updated_at": _now(),
            "messages": [],
        }
        data["sessions"].append(s)
        _save(data)
        return s


def delete_session(sid: str) -> bool:
    with _LOCK:
        data = _load()
        before = len(data["sessions"])
        data["sessions"] = [s for s in data["sessions"] if s["id"] != sid]
        _save(data)
        return len(data["sessions"]) != before


def clear_session(sid: str) -> bool:
    with _LOCK:
        data = _load()
        for s in data["sessions"]:
            if s["id"] == sid:
                s["messages"] = []
                s["title"] = ""
                s["updated_at"] = _now()
                _save(data)
                return True
        return False


def append(sid: str, role: str, content: str) -> None:
    with _LOCK:
        data = _load()
        for s in data["sessions"]:
            if s["id"] == sid:
                s.setdefault("messages", []).append({"role": role, "content": content})
                if role == "user" and not s.get("title"):
                    s["title"] = " ".join(content.split())[:48]
                s["updated_at"] = _now()
                _save(data)
                return

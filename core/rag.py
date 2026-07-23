"""RAG local para o chat global — sem gastar token.

No fim do processamento de cada reunião, indexamos a transcrição: quebramos em
trechos, geramos *embeddings* locais (fastembed/ONNX, roda em CPU) e salvamos os
vetores ao lado da reunião. O chat global recupera só os trechos mais parecidos
com a pergunta e manda apenas isso para a IA — barato e escalável.

Degradação graciosa: se o fastembed não estiver instalado, `search()` devolve
None e o chamador cai no modo antigo (mandar as transcrições inteiras).

Arquivos por reunião (na pasta da reunião):
    rag_vecs.npy     matriz float32 N×D, L2-normalizada
    rag_chunks.json  [{start, text}] alinhado às linhas de rag_vecs
"""
from __future__ import annotations

import json
import logging
import re
import threading

import numpy as np

from core.config import DATA_DIR

_log = logging.getLogger(__name__)

# Modelo multilíngue pequeno (bom em PT), roda em CPU via onnxruntime.
_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_CACHE_DIR = str(DATA_DIR / "rag_models")

_SEG_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s+([^:]+?):\s+(.*)$")

_model = None
_model_failed = False
_lock = threading.Lock()


def _fmt_clock(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def available() -> bool:
    return _get_model() is not None


def _get_model():
    """Carrega o modelo de embedding uma vez. None se indisponível."""
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        return None
    with _lock:
        if _model is not None:
            return _model
        if _model_failed:
            return None
        try:
            from fastembed import TextEmbedding

            names = {m["model"] for m in TextEmbedding.list_supported_models()}
            name = _MODEL_NAME if _MODEL_NAME in names else next(iter(names))
            _log.info("Carregando modelo de embedding do RAG: %s", name)
            _model = TextEmbedding(model_name=name, cache_dir=_CACHE_DIR)
        except Exception as exc:  # noqa: BLE001 — sem fastembed/modelo: desliga o RAG
            _log.warning("RAG indisponível (embeddings desligados): %s", exc)
            _model_failed = True
            _model = None
        return _model


def _embed(texts: list[str]) -> np.ndarray | None:
    model = _get_model()
    if model is None or not texts:
        return None
    vecs = np.asarray(list(model.embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / (norms + 1e-9)  # L2-normaliza -> produto interno = cosseno


def _parse_segments(transcript: str) -> list[dict]:
    segs: list[dict] = []
    for line in (transcript or "").splitlines():
        m = _SEG_RE.match(line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            segs.append(
                {"start": h * 3600 + mi * 60 + s, "speaker": m.group(4).strip(), "text": m.group(5).strip()}
            )
        elif segs and line.strip():
            segs[-1]["text"] += " " + line.strip()
    return segs


def _chunk(segments: list[dict], max_chars: int = 600) -> list[dict]:
    """Agrupa falas em trechos ~max_chars. Cada trecho guarda o tempo de início,
    o texto para a IA (com [HH:MM:SS]) e o texto para embedding (sem timestamps)."""
    chunks: list[dict] = []
    disp: list[str] = []
    emb: list[str] = []
    start = None
    for s in segments:
        if start is None:
            start = s["start"]
        who = s["speaker"].replace("_", " ")
        disp.append(f"[{_fmt_clock(s['start'])}] {who}: {s['text']}")
        emb.append(f"{who}: {s['text']}")
        if sum(len(x) for x in emb) >= max_chars:
            chunks.append({"start": start, "text": "\n".join(disp), "embed": " ".join(emb)})
            disp, emb, start = [], [], None
    if emb:
        chunks.append({"start": start, "text": "\n".join(disp), "embed": " ".join(emb)})
    return chunks


def _paths(meeting):
    from pathlib import Path

    d = Path(meeting.dir_path)
    return d / "rag_vecs.npy", d / "rag_chunks.json", d / "transcript.txt"


def index_meeting(meeting) -> bool:
    """Indexa (ou reindexa) a transcrição da reunião. True se gerou índice."""
    vecs_p, chunks_p, tr_p = _paths(meeting)
    transcript = ""
    if meeting.transcript_path:
        from pathlib import Path

        p = Path(meeting.transcript_path)
        if p.exists():
            transcript = p.read_text(encoding="utf-8")
    if not transcript and tr_p.exists():
        transcript = tr_p.read_text(encoding="utf-8")
    chunks = _chunk(_parse_segments(transcript))
    if not chunks:
        return False
    vecs = _embed([c["embed"] for c in chunks])
    if vecs is None:
        return False
    try:
        np.save(vecs_p, vecs)
        chunks_p.write_text(
            json.dumps([{"start": c["start"], "text": c["text"]} for c in chunks], ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("Falha ao salvar índice RAG de %s: %s", meeting.id, exc)
        return False


def ensure_index(meeting):
    """Devolve (vecs, chunks) do índice, construindo se faltar/estiver velho."""
    vecs_p, chunks_p, tr_p = _paths(meeting)
    fresh = (
        vecs_p.exists()
        and chunks_p.exists()
        and (not tr_p.exists() or vecs_p.stat().st_mtime >= tr_p.stat().st_mtime)
    )
    if not fresh:
        if not index_meeting(meeting):
            return None
    try:
        vecs = np.load(vecs_p)
        chunks = json.loads(chunks_p.read_text(encoding="utf-8"))
        if len(chunks) != len(vecs):
            return None
        return vecs, chunks
    except Exception:  # noqa: BLE001
        return None


def search(query: str, meetings: list, top_k: int = 8) -> list[dict] | None:
    """Trechos mais parecidos com a pergunta, entre as reuniões dadas.

    None => RAG indisponível (o chamador deve usar o modo antigo).
    """
    qv = _embed([query])
    if qv is None:
        return None
    qv = qv[0]
    rows: list[tuple[float, str, int, str]] = []
    for m in meetings:
        if m is None:
            continue
        idx = ensure_index(m)
        if idx is None:
            continue
        vecs, chunks = idx
        sims = vecs @ qv
        for i, sc in enumerate(sims):
            rows.append((float(sc), m.id, chunks[i]["start"], chunks[i]["text"]))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [
        {"meeting_id": mid, "start": start, "text": text, "score": sc}
        for (sc, mid, start, text) in rows[:top_k]
    ]

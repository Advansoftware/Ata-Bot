"""Transcrição local com faster-whisper.

O bot grava uma faixa .wav por participante (o Pycord entrega áudio por-usuário),
então sabemos quem falou o quê. Transcrevemos cada faixa, marcamos o falante,
e juntamos tudo ordenado no tempo — o que dá uma transcrição já com falantes,
ideal para a ata.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from faster_whisper import WhisperModel

from core import models
from core.config import TranscriptionConfig


@dataclass
class Segment:
    start: float
    speaker: str
    text: str


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path)) as w:
            rate = w.getframerate() or 1
            return w.getnframes() / float(rate)
    except Exception:  # noqa: BLE001
        return 0.0


class Transcriber:
    def __init__(self, cfg: TranscriptionConfig):
        # O modelo é carregado uma vez e reutilizado (é caro carregar).
        # ensure() aponta para data/models/<nome> (baixa antes se faltar).
        model_ref = models.ensure(cfg.model)
        self.model = WhisperModel(
            model_ref, device=cfg.device, compute_type=cfg.compute_type
        )

    def transcribe_track(
        self,
        path: Path,
        speaker: str,
        language: str,
        on_seg: Optional[Callable[[float], None]] = None,
    ) -> list[Segment]:
        # "auto"/vazio => deixa o Whisper detectar o idioma sozinho.
        lang = None if (language or "").lower() in ("", "auto") else language
        segments, _info = self.model.transcribe(str(path), language=lang)
        out: list[Segment] = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                out.append(Segment(start=seg.start, speaker=speaker, text=text))
            if on_seg is not None:
                on_seg(seg.end)  # posição (s) já transcrita, p/ o % de progresso
        return out

    def transcribe_meeting(
        self,
        tracks: dict[str, Path],
        language: str,
        on_track: Optional[Callable[[int, int, str], None]] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> list[Segment]:
        """tracks: {nome_do_falante: caminho_do_wav}. Retorna segmentos ordenados.

        on_track(feito, total, falante): antes de cada faixa (ex.: '2/3 — Fulano').
        on_progress(frac 0..1): fração do ÁUDIO total já transcrita — para uma
        barra de progresso real enquanto a transcrição roda (ela é lenta na CPU).
        """
        durations = {sp: _wav_duration(p) for sp, p in tracks.items()}
        total_dur = sum(durations.values()) or 1.0
        base = 0.0
        all_segments: list[Segment] = []
        total = len(tracks)
        for i, (speaker, path) in enumerate(tracks.items(), 1):
            if on_track:
                on_track(i, total, speaker)
            dur = durations.get(speaker, 0.0)

            def _seg(end: float, _base=base, _dur=dur) -> None:
                if on_progress is not None:
                    frac = (_base + min(end, _dur)) / total_dur
                    on_progress(max(0.0, min(0.999, frac)))

            all_segments.extend(self.transcribe_track(path, speaker, language, on_seg=_seg))
            base += dur
            if on_progress is not None:
                on_progress(min(0.999, base / total_dur))
        all_segments.sort(key=lambda s: s.start)
        if on_progress is not None:
            on_progress(1.0)
        return all_segments


def render_transcript(segments: Iterable[Segment]) -> str:
    """Transcrição em texto legível, com falantes."""
    lines = []
    for seg in segments:
        stamp = _fmt_time(seg.start)
        lines.append(f"[{stamp}] {seg.speaker}: {seg.text}")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

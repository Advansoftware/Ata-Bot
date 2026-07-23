"""Orquestra o pós-reunião: transcrever faixas -> gerar ata -> salvar.

Roda o trabalho pesado (Whisper na CPU, chamada ao LLM) em thread separada
para não travar o event loop do Discord.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Optional

from core import storage
from core.config import Config
from core.minutes import get_provider
from core.minutes.base import MeetingMeta
from core.minutes.condense import condense_if_needed
from core.transcriber import Transcriber, render_transcript

# on_step(etapa, detalhe): etapa em {"transcribe","generate","done"}.
StepCB = Callable[[str, str], None]


class Pipeline:
    def __init__(self, cfg: Config):
        # Carrega o modelo do Whisper uma vez (custoso) e reaproveita.
        self.transcriber = Transcriber(cfg.transcription)
        self.language = cfg.language

    async def process(
        self,
        meeting: storage.Meeting,
        tracks: dict[str, Path],
        on_step: Optional[StepCB] = None,
    ) -> storage.Meeting:
        """tracks: {nome_do_falante: caminho_do_wav}. Retorna a reunião atualizada."""
        storage.update_meeting(meeting.id, status="processing", ended_at=True)
        try:
            transcript, minutes = await asyncio.to_thread(
                self._run_sync, meeting, tracks, on_step
            )
        except Exception:
            storage.update_meeting(meeting.id, status="error")
            raise

        transcript_path = meeting.dir / "transcript.txt"
        minutes_path = meeting.dir / "minutes.md"
        transcript_path.write_text(transcript, encoding="utf-8")
        minutes_path.write_text(minutes, encoding="utf-8")

        storage.update_meeting(
            meeting.id,
            status="done",
            transcript_path=str(transcript_path),
            minutes_path=str(minutes_path),
        )
        return storage.get_meeting(meeting.id)  # type: ignore[return-value]

    def _run_sync(
        self,
        meeting: storage.Meeting,
        tracks: dict[str, Path],
        on_step: Optional[StepCB] = None,
    ) -> tuple[str, str]:
        step = on_step or (lambda _k, _d="": None)

        # 1) Transcrição (só depois da gravação encerrada), faixa por faixa.
        def _on_track(done, total, speaker):
            step("transcribe", f"{done}/{total} — {speaker}")

        segments = self.transcriber.transcribe_meeting(
            tracks, self.language, on_track=_on_track
        )
        transcript = render_transcript(segments)

        # 2) Geração da ata: lê provedor/chave atuais (mudanças valem sem reiniciar).
        cfg = Config.load()
        provider = get_provider(cfg.minutes)
        meta = MeetingMeta(
            started_at=meeting.started_at,
            ended_at=meeting.ended_at,
            participants=list(tracks.keys()),
            language=cfg.language,
        )

        # Protege o contexto: condensa a transcrição se ela for muito longa.
        def _on_cond(done, total):
            step("generate", f"condensando trecho {done}/{total}")

        prepared = condense_if_needed(transcript, provider, on_progress=_on_cond)

        step("generate", "escrevendo a ata")
        minutes = provider.generate(prepared, meta)
        step("done", "")
        return transcript, minutes

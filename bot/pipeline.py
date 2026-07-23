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
        """tracks: {nome_do_falante: caminho_do_wav}. Retorna a reunião atualizada.

        As etapas são persistidas em disco à medida que terminam (transcript.txt
        assim que a transcrição fica pronta, minutes.md ao final), para o dashboard
        conseguir mostrar em qual etapa a reunião está enquanto processa.
        """
        storage.update_meeting(meeting.id, status="processing", ended_at=True)
        transcript_path = meeting.dir / "transcript.txt"
        minutes_path = meeting.dir / "minutes.md"
        try:
            # 1) Transcrição — salva o transcript.txt assim que fica pronto.
            transcript = await asyncio.to_thread(self._transcribe, meeting, tracks, on_step)
            transcript_path.write_text(transcript, encoding="utf-8")
            storage.update_meeting(meeting.id, transcript_path=str(transcript_path))

            # 2) Geração da ata.
            minutes = await asyncio.to_thread(
                self._generate, meeting, tracks, transcript, on_step
            )
            minutes_path.write_text(minutes, encoding="utf-8")
        except Exception:
            storage.update_meeting(meeting.id, status="error")
            raise

        (meeting.dir / "progress.json").unlink(missing_ok=True)  # limpa o progresso
        storage.update_meeting(
            meeting.id,
            status="done",
            minutes_path=str(minutes_path),
        )
        updated = storage.get_meeting(meeting.id)

        # Última etapa: indexa a transcrição para o RAG (chat global), em background
        # e à prova de falhas — não deve atrapalhar o término da reunião.
        try:
            import threading

            from core import rag

            threading.Thread(target=rag.index_meeting, args=(updated,), daemon=True).start()
        except Exception:  # noqa: BLE001
            pass
        return updated  # type: ignore[return-value]

    def _transcribe(
        self,
        meeting: storage.Meeting,
        tracks: dict[str, Path],
        on_step: Optional[StepCB] = None,
    ) -> str:
        """Etapa 1: transcreve as faixas (roda em thread). Só depois da gravação.

        Grava o progresso (0..1) em <reunião>/progress.json para o dashboard
        mostrar uma barra de % — a transcrição é lenta na CPU.
        """
        import json

        step = on_step or (lambda _k, _d="": None)
        progress_path = meeting.dir / "progress.json"
        last_pct = {"v": -1}

        def _on_track(done, total, speaker):
            step("transcribe", f"{done}/{total} — {speaker}")

        def _on_progress(frac: float) -> None:
            pct = int(frac * 100)
            if pct == last_pct["v"]:  # só grava quando o % inteiro muda
                return
            last_pct["v"] = pct
            try:
                progress_path.write_text(
                    json.dumps({"stage": "transcribe", "frac": round(frac, 4)}),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001
                pass

        segments = self.transcriber.transcribe_meeting(
            tracks, self.language, on_track=_on_track, on_progress=_on_progress
        )
        return render_transcript(segments)

    def _generate(
        self,
        meeting: storage.Meeting,
        tracks: dict[str, Path],
        transcript: str,
        on_step: Optional[StepCB] = None,
    ) -> str:
        """Etapa 2: gera a ata a partir do transcript (roda em thread)."""
        step = on_step or (lambda _k, _d="": None)

        # Lê provedor/chave atuais (mudanças valem sem reiniciar).
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
        return minutes

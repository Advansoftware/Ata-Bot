"""Ponte Python <-> JavaScript exposta ao webview (pywebview js_api).

A UI (HTML/JS) chama estes métodos via `pywebview.api.<metodo>(...)`.
Chaves de API nunca são devolvidas para a UI — só um indicador de "configurada".
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import webview

from app.botrunner import BotRunner
from core import storage
from core.config import PROVIDERS, Config, read_raw, save_raw

_SEG_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s+([^:]+?):\s+(.*)$")


def _parse_segments(transcript: str) -> list[dict]:
    """Converte 'transcript.txt' ([HH:MM:SS] Falante: texto) em segmentos com o
    tempo em segundos — para o transcript clicável sincronizado com o player."""
    segs: list[dict] = []
    for line in (transcript or "").splitlines():
        m = _SEG_RE.match(line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            segs.append(
                {"start": h * 3600 + mi * 60 + s, "speaker": m.group(4).strip(), "text": m.group(5).strip()}
            )
        elif segs and line.strip():
            segs[-1]["text"] += " " + line.strip()  # continuação de uma fala longa
    return segs


def _snippet(text: str, query: str, ctx: int = 60) -> str:
    low = text.lower()
    i = low.find(query.lower())
    if i < 0:
        return text[:120].replace("\n", " ").strip()
    start, end = max(0, i - ctx), min(len(text), i + len(query) + ctx)
    s = text[start:end].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + s + ("…" if end < len(text) else "")


def _short_subject(text: str, limit: int = 90) -> str:
    """Primeira frase de `text`, limpa de markdown e truncada — vira o 'assunto'."""
    text = text.replace("*", "").replace("#", "").strip()
    for sep in (". ", "! ", "? "):
        if sep in text:
            text = text.split(sep, 1)[0] + sep.strip()
            break
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _derive_subject(minutes: str) -> str:
    """Deduz um assunto curto a partir da ata (minutes.md)."""
    if not minutes:
        return ""
    lines = minutes.splitlines()
    # 1) Preferir a 1ª frase de conteúdo da seção "Resumo".
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## resumo"):
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if s and not s.startswith(("#", "---", "**", "*", ">")):
                    return _short_subject(s)
            break
    # 2) Senão, a 1ª linha significativa que não seja título/metadado.
    for line in lines:
        s = line.strip().lstrip("#").strip()
        low = s.lower()
        if not s or s.startswith("---"):
            continue
        if low.startswith("ata de reuni"):
            continue
        if s.startswith("**") and ":" in s:  # linhas de metadados (Data:, Horário:)
            continue
        return _short_subject(s)
    return ""


class Api:
    def __init__(self):
        self.window = None
        self.runner = BotRunner(self.log)
        self._transcriber = None  # carregado sob demanda no primeiro teste
        self._test_rec = None
        self._model_dl = None  # thread do download de modelo em andamento

    def set_window(self, window) -> None:
        self.window = window

    # ---- Ponte para a UI: roda um trecho de JS com segurança ----

    def _emit(self, js: str) -> None:
        if self.window is not None:
            try:
                self.window.evaluate_js(js)
            except Exception:
                pass  # janela pode ter sido fechada

    def log(self, message: str) -> None:
        self._emit(f"window.appendLog({json.dumps(str(message))})")

    def _step(self, key: str, detail: str = "") -> None:
        """Atualiza o passo-a-passo visual do teste na UI."""
        self._emit(f"window.pipelineStep({json.dumps(key)},{json.dumps(detail)})")

    # ---- Configuração ----

    def get_settings(self) -> dict:
        """Devolve settings para a UI, com segredos MASCARADOS (só flag de presença)."""
        raw = read_raw()
        out = {
            "discord_token_set": bool(raw.get("discord_token", "").strip()),
            "language": raw.get("language", "pt"),
            "post_to_discord": bool(raw.get("post_to_discord", True)),
            "output_dir": raw.get("output_dir", ""),
            "webhook_url": raw.get("webhook_url", ""),
            "default_output_dir": str(Config.load().resolved_output_dir()),
            "mic_device": raw.get("mic_device", None),
            "transcription": raw.get("transcription", {}),
            "minutes": {"provider": raw["minutes"].get("provider", "claude")},
        }
        for p in PROVIDERS:
            prov = dict(raw["minutes"].get(p, {}))
            has_key = bool(prov.get("api_key", "").strip())
            prov.pop("api_key", None)
            prov["api_key_set"] = has_key
            out["minutes"][p] = prov
        return out

    def save_settings(self, data: dict) -> dict:
        """Recebe o formulário da UI e grava. Campo de chave vazio = mantém a atual."""
        raw = read_raw()

        # Token do Discord: vazio = mantém.
        token = (data.get("discord_token") or "").strip()
        if token:
            raw["discord_token"] = token

        raw["language"] = (data.get("language") or raw.get("language") or "pt").strip()

        # Postar a ata no canal do Discord (checkbox). Só atualiza se veio no payload.
        if "post_to_discord" in data:
            raw["post_to_discord"] = bool(data.get("post_to_discord"))

        # Pasta de destino: string vazia = volta ao padrão (data/meetings).
        if "output_dir" in data:
            raw["output_dir"] = (data.get("output_dir") or "").strip()

        # URL de webhook para enviar/compartilhar a ata.
        if "webhook_url" in data:
            raw["webhook_url"] = (data.get("webhook_url") or "").strip()

        # Microfone do teste: índice (int) ou None = padrão do SO.
        if "mic_device" in data:
            dev = data.get("mic_device")
            raw["mic_device"] = int(dev) if isinstance(dev, (int, float)) else None

        tr = data.get("transcription") or {}
        for k in ("model", "device", "compute_type"):
            if tr.get(k):
                raw["transcription"][k] = tr[k]

        mn = data.get("minutes") or {}
        provider = (mn.get("provider") or raw["minutes"]["provider"]).lower()
        if provider in PROVIDERS:
            raw["minutes"]["provider"] = provider

        for p in PROVIDERS:
            incoming = mn.get(p) or {}
            if incoming.get("model"):
                raw["minutes"][p]["model"] = incoming["model"]
            if p == "ollama":
                if incoming.get("host"):
                    raw["minutes"][p]["host"] = incoming["host"]
            else:
                # Chave: só sobrescreve se veio algo (vazio = mantém a atual).
                new_key = (incoming.get("api_key") or "").strip()
                if new_key:
                    raw["minutes"][p]["api_key"] = new_key

        save_raw(raw)
        cfg = Config.load()
        return {
            "ok": True,
            "configured": cfg.is_configured(),
            "provider_ready": cfg.provider_ready(),
        }

    def list_ollama_models(self, host: str) -> list[str]:
        """Lista os modelos já baixados no Ollama local (GET {host}/api/tags)."""
        try:
            import httpx

            host = (host or "http://localhost:11434").rstrip("/")
            resp = httpx.get(f"{host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return [m for m in models if m]
        except Exception as e:  # noqa: BLE001
            self.log(f"Não foi possível consultar o Ollama em {host}: {e}")
            return []

    # ---- Modelos do Whisper: estado + download com progresso ----

    def model_status(self) -> dict:
        """{ nome_do_modelo: baixado? } para todos os modelos conhecidos."""
        from core import models

        return {n: models.is_downloaded(n) for n in models.WHISPER_MODELS}

    def download_model(self, name: str) -> dict:
        """Baixa o modelo em thread própria; progresso vai via window.modelProgress."""
        from core import models

        if name not in models.WHISPER_MODELS:
            return {"error": f"Modelo desconhecido: {name}"}
        if self._model_dl is not None and self._model_dl.is_alive():
            return {"error": "Já há um download em andamento."}

        safe_name = json.dumps(name)

        def run():
            try:
                self.log(f"⬇ Baixando modelo '{name}'...")
                last_pct = [-1]  # só emite quando o percentual inteiro muda

                def on_progress(frac, done, total):
                    pct = int(frac * 100)
                    if pct == last_pct[0]:
                        return
                    last_pct[0] = pct
                    self._emit(
                        f"window.modelProgress({safe_name},{frac},{done},{total})"
                    )

                models.download(name, on_progress)
                self.log(f"✅ Modelo '{name}' baixado.")
                self._emit(f"window.modelDone({safe_name},true,'')")
            except Exception as e:  # noqa: BLE001
                self.log(f"❌ Falha ao baixar '{name}': {e}")
                self._emit(f"window.modelDone({safe_name},false,{json.dumps(str(e))})")

        self._model_dl = threading.Thread(target=run, daemon=True)
        self._model_dl.start()
        return {"started": True}

    # ---- Microfone: lista de dispositivos de entrada ----

    def list_audio_devices(self) -> dict:
        try:
            import sounddevice as sd
        except Exception as e:  # noqa: BLE001 — sounddevice/PortAudio ausente
            return {"error": str(e), "devices": []}
        try:
            default_in = sd.default.device[0]
        except Exception:
            default_in = None
        devices = []
        try:
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_input_channels", 0) > 0:
                    devices.append(
                        {
                            "index": i,
                            "name": d.get("name", f"Dispositivo {i}"),
                            "default": i == default_in,
                        }
                    )
        except Exception as e:  # noqa: BLE001
            return {"error": str(e), "devices": []}
        return {"devices": devices}

    # ---- Teste rápido (sem Discord): microfone -> transcrição -> mini-ata ----

    def _get_transcriber(self):
        if self._transcriber is None:
            from core.config import Config
            from core.transcriber import Transcriber

            self.log("Carregando modelo de transcrição para o teste (primeira vez pode demorar)...")
            self._transcriber = Transcriber(Config.load().transcription)
        return self._transcriber

    def start_test(self) -> dict:
        try:
            from app.testrec import TestRecorder
        except Exception as e:  # noqa: BLE001 — sounddevice/PortAudio ausente
            import sys

            hint = ""
            if sys.platform.startswith("linux"):
                hint = (
                    " — falta a lib de sistema PortAudio. Instale com:"
                    " sudo apt install libportaudio2  (ou dnf/pacman install portaudio)."
                )
            return {"error": f"Gravação indisponível (microfone): {e}{hint}"}
        if self._test_rec is not None and self._test_rec.recording:
            return {"error": "Já está gravando."}
        device = read_raw().get("mic_device")
        try:
            self._test_rec = TestRecorder(device=device)
            self._test_rec.start()
        except Exception as e:  # noqa: BLE001
            return {"error": f"Não consegui acessar o microfone: {e}"}
        self.log("🎤 Gravando teste... fale algo e clique em Parar.")
        return {"recording": True}

    def test_level(self) -> float:
        """Nível atual do microfone (0..1) para o medidor visual."""
        if self._test_rec is not None and self._test_rec.recording:
            return float(self._test_rec.level)
        return 0.0

    def stop_test(self) -> dict:
        from core.config import DATA_DIR, Config

        if self._test_rec is None or not self._test_rec.recording:
            return {"error": "Nada gravando."}

        # Passo 1: salvar o áudio gravado (a gravação já terminou).
        self._step("save", "salvando o áudio")
        test_dir = DATA_DIR / "_teste"
        test_dir.mkdir(parents=True, exist_ok=True)
        wav_path = test_dir / "ultimo_teste.wav"
        self._test_rec.stop(wav_path)

        cfg = Config.load()

        # Passo 2: transcrever (só depois da gravação encerrada).
        self._step("transcribe", "1/1 — Você")
        self.log("Transcrevendo o áudio de teste...")
        try:
            from core.transcriber import render_transcript

            segments = self._get_transcriber().transcribe_meeting(
                {"Você": wav_path}, cfg.language
            )
            transcript = render_transcript(segments)
        except Exception as e:  # noqa: BLE001
            self._step("done", "")
            return {"error": f"Erro na transcrição: {e}"}

        if not transcript.strip():
            self._step("done", "")
            return {
                "transcript": "",
                "minutes": "",
                "warning": "Não captei nenhuma fala. Verifique o microfone e fale mais alto/perto.",
            }

        # Passo 3: gerar a ata com a IA (só depois da transcrição pronta).
        minutes, err = "", ""
        if cfg.provider_ready():
            try:
                from core.minutes import get_provider
                from core.minutes.base import MeetingMeta
                from core.minutes.condense import condense_if_needed

                provider = get_provider(cfg.minutes)

                def _on_cond(done, total):
                    self._step("generate", f"condensando trecho {done}/{total}")

                prepared = condense_if_needed(
                    transcript, provider, log=self.log, on_progress=_on_cond
                )

                self._step("generate", "escrevendo a ata")
                self.log("Gerando a mini-ata com o provedor configurado...")
                minutes = provider.generate(
                    prepared,
                    MeetingMeta(
                        started_at="teste local",
                        ended_at=None,
                        participants=["Você"],
                        language=cfg.language,
                    ),
                )
            except Exception as e:  # noqa: BLE001
                err = f"Transcrição OK, mas falhou ao gerar a ata: {e}"
        else:
            err = "Provedor da ata não configurado — mostrando só a transcrição."

        self._step("done", "")
        self.log("✅ Teste concluído.")
        return {"transcript": transcript, "minutes": minutes, "error": err}

    def choose_folder(self) -> str:
        """Abre o seletor de pasta nativo do SO e devolve o caminho escolhido."""
        if self.window is None:
            return ""
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            return result[0]
        return ""

    # ---- Controle do bot ----

    def start_bot(self) -> dict:
        msg = self.runner.start()
        return {"message": msg, "running": self.runner.running}

    def stop_bot(self) -> dict:
        msg = self.runner.stop()
        return {"message": msg, "running": self.runner.running}

    def status(self) -> dict:
        cfg = Config.load()
        return {
            "running": self.runner.running,
            "configured": cfg.is_configured(),
            "provider": cfg.minutes.provider,
        }

    # ---- Reuniões gravadas (dashboard) ----

    @staticmethod
    def _read_text(path) -> str:
        try:
            p = Path(path)
            return p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:  # noqa: BLE001
            return ""

    def list_recordings(self) -> list[dict]:
        """Lista as reuniões para o dashboard (assunto, data, participantes, estado)."""
        storage.init_db()
        out = []
        for m in storage.list_meetings(limit=200):
            d = Path(m.dir_path)
            minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
            participants = (
                sorted(f.stem for f in d.glob("*.wav")) if d.exists() else []
            )
            transcript_ok = bool(self._read_text(m.transcript_path).strip()) or (
                d / "transcript.txt"
            ).exists()
            has_minutes = bool(minutes.strip())
            # Etapa atual (só importa enquanto processa/grava), inferida do que já
            # existe em disco: sem transcript ainda => transcrevendo; com transcript
            # mas sem ata => gerando a ata.
            stage = None
            if m.status == "recording":
                stage = "recording"
            elif m.status == "processing":
                stage = "transcribe" if not transcript_ok else "generate"
            out.append(
                {
                    "id": m.id,
                    "subject": _derive_subject(minutes) or "Reunião sem ata",
                    "started_at": m.started_at,
                    "ended_at": m.ended_at,
                    "status": m.status,
                    "stage": stage,
                    "participants": participants,
                    "has_minutes": has_minutes,
                    "has_transcript": transcript_ok,
                }
            )
        return out

    def get_recording(self, meeting_id: str) -> dict:
        """Conteúdo completo de uma reunião: ata (markdown), transcrição e áudios."""
        m = storage.get_meeting(meeting_id)
        if m is None:
            return {"error": "Reunião não encontrada."}
        d = Path(m.dir_path)
        minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
        transcript = self._read_text(m.transcript_path) or self._read_text(
            d / "transcript.txt"
        )
        audio = []
        if d.exists():
            wavs = sorted(d.glob("*.wav"))
            base_url = ""
            if wavs:
                try:
                    from app.audioserver import ensure_server

                    base_url = f"http://127.0.0.1:{ensure_server()}/audio/{m.id}"
                except Exception:  # noqa: BLE001 — sem player, mas o resto funciona
                    base_url = ""
            for f in wavs:
                audio.append(
                    {
                        "name": f.name,
                        "stem": f.stem,  # casa com o 'speaker' dos segmentos
                        "speaker": f.stem.replace("_", " "),
                        "size": f.stat().st_size,
                        "url": f"{base_url}/{f.name}" if base_url else "",
                    }
                )
        return {
            "id": m.id,
            "subject": _derive_subject(minutes) or "Reunião sem ata",
            "started_at": m.started_at,
            "ended_at": m.ended_at,
            "status": m.status,
            "participants": sorted(a["name"].rsplit(".", 1)[0] for a in audio),
            "minutes": minutes,
            "transcript": transcript,
            "segments": _parse_segments(transcript),
            "audio_files": audio,
            "dir": str(d),
        }

    def open_meeting_folder(self, meeting_id: str) -> dict:
        """Abre a pasta da reunião no gerenciador de arquivos do sistema."""
        import os
        import subprocess
        import sys

        m = storage.get_meeting(meeting_id)
        if m is None or not Path(m.dir_path).exists():
            return {"error": "Pasta não encontrada."}
        path = m.dir_path
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]  # noqa
            else:
                subprocess.Popen(["xdg-open", path])
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def delete_recording(self, meeting_id: str) -> dict:
        """Apaga a reunião (índice + pasta em disco)."""
        ok = storage.delete_meeting(meeting_id)
        return {"ok": ok}

    # ---- Chat com as reuniões (pergunta à IA sobre o histórico) ----

    def _full_context_blocks(self, meetings: list, budget: int = 60000) -> tuple[list, int]:
        """Modo antigo (fallback): empilha transcrições inteiras até o orçamento."""
        blocks, used = [], 0
        for m in meetings:
            if m is None:
                continue
            d = Path(m.dir_path)
            tr = self._read_text(m.transcript_path) or self._read_text(d / "transcript.txt")
            if not tr.strip():
                continue
            minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
            subject = _derive_subject(minutes) or "Reunião"
            block = f"### {subject} ({m.started_at[:10]}) — id={m.id}\n{tr}"
            room = budget - sum(len(b) for b in blocks)
            if len(block) > room:
                if room > 500:
                    blocks.append(block[:room])
                    used += 1
                break
            blocks.append(block)
            used += 1
        return blocks, used

    def ask_meetings(self, question: str, meeting_id: str | None = None) -> dict:
        """Responde uma pergunta com base nas transcrições.

        - Reunião específica (balão): usa a transcrição inteira daquela reunião.
        - Chat global: usa RAG (recupera só os trechos relevantes de todas as
          reuniões) para não enviar tudo à IA e gastar token à toa. Se o RAG não
          estiver disponível, cai no modo antigo (transcrições inteiras).
        """
        question = (question or "").strip()
        if not question:
            return {"error": "Digite uma pergunta."}
        cfg = Config.load()
        if not cfg.provider_ready():
            return {"error": "Configure um provedor de IA (com chave) para usar o chat."}

        mode = "full"
        if meeting_id:
            blocks, used = self._full_context_blocks([storage.get_meeting(meeting_id)])
        else:
            from core import rag

            hits = rag.search(question, storage.list_meetings(limit=500), top_k=8)
            if hits is not None:  # RAG disponível
                mode = "rag"
                blocks, seen = [], set()
                for h in hits:
                    m = storage.get_meeting(h["meeting_id"])
                    if m is None:
                        continue
                    seen.add(m.id)
                    minutes = self._read_text(m.minutes_path) or self._read_text(
                        Path(m.dir_path) / "minutes.md"
                    )
                    subject = _derive_subject(minutes) or "Reunião"
                    blocks.append(f"### {subject} ({m.started_at[:10]}) — id={m.id}\n{h['text']}")
                used = len(seen)
            else:  # sem fastembed: modo antigo
                blocks, used = self._full_context_blocks(storage.list_meetings(limit=200))

        if not blocks:
            return {"error": "Nenhuma transcrição disponível para consultar."}

        system = (
            "Você é um assistente que responde perguntas sobre reuniões, baseado APENAS "
            "nas transcrições fornecidas. Responda em português do Brasil, de forma "
            "objetiva e em Markdown. Se a resposta não estiver nas transcrições, diga "
            "claramente que não encontrou.\n"
            "IMPORTANTE — citações: ao afirmar algo que veio de um trecho específico, "
            "adicione logo depois uma citação clicável no formato exato "
            "[[<id da reunião>@HH:MM:SS]], usando o id do cabeçalho da reunião e o "
            "horário [HH:MM:SS] da fala correspondente. Ex.: [[a1b2c3d4e5f6@00:04:12]]. "
            "Não invente ids nem horários; use os que aparecem no contexto."
        )
        user = f"Transcrições disponíveis:\n\n{chr(10).join(blocks)}\n\n---\nPergunta: {question}"
        try:
            from core.minutes import get_provider

            answer = get_provider(cfg.minutes).complete(system, user, max_tokens=1500)
        except Exception as e:  # noqa: BLE001
            return {"error": f"Erro ao consultar a IA: {e}"}
        return {"answer": answer, "meetings_used": used, "mode": mode}

    # ---- Sessões do chat global ----

    def chat_sessions(self) -> list[dict]:
        from core import chatsessions

        return chatsessions.list_sessions()

    def get_chat_session(self, session_id: str) -> dict:
        from core import chatsessions

        s = chatsessions.get_session(session_id)
        return s or {"error": "Sessão não encontrada."}

    def new_chat_session(self) -> dict:
        from core import chatsessions

        return chatsessions.create_session()

    def delete_chat_session(self, session_id: str) -> dict:
        from core import chatsessions

        return {"ok": chatsessions.delete_session(session_id)}

    def clear_chat_session(self, session_id: str) -> dict:
        from core import chatsessions

        return {"ok": chatsessions.clear_session(session_id)}

    def chat(self, session_id: str | None, question: str) -> dict:
        """Chat global com sessão: responde (RAG) e persiste a conversa."""
        from core import chatsessions

        if not session_id or chatsessions.get_session(session_id) is None:
            session_id = chatsessions.create_session()["id"]
        r = self.ask_meetings(question, None)
        if r.get("error"):
            return {"error": r["error"], "session_id": session_id}
        chatsessions.append(session_id, "user", question)
        chatsessions.append(session_id, "assistant", r["answer"])
        return {"answer": r["answer"], "mode": r.get("mode"), "session_id": session_id}

    # ---- Busca global ----

    def search_meetings(self, query: str) -> list[dict]:
        """Procura o termo no assunto, na transcrição e na ata de todas as reuniões."""
        q = (query or "").strip().lower()
        if not q:
            return []
        results = []
        for m in storage.list_meetings(limit=300):
            d = Path(m.dir_path)
            minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
            transcript = self._read_text(m.transcript_path) or self._read_text(
                d / "transcript.txt"
            )
            subject = _derive_subject(minutes) or "Reunião sem ata"
            where, snippet = None, ""
            if q in subject.lower():
                where, snippet = "assunto", subject
            elif transcript and q in transcript.lower():
                where, snippet = "transcrição", _snippet(transcript, q)
            elif minutes and q in minutes.lower():
                where, snippet = "ata", _snippet(minutes, q)
            if where:
                results.append(
                    {
                        "id": m.id,
                        "subject": subject,
                        "started_at": m.started_at,
                        "status": m.status,
                        "where": where,
                        "snippet": snippet,
                    }
                )
        return results

    # ---- Itens de ação consolidados (Tarefas) ----

    def list_action_items(self) -> list[dict]:
        from core import tasks

        state = tasks.load_state()
        out = []
        for m in storage.list_meetings(limit=300):
            d = Path(m.dir_path)
            minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
            if not minutes.strip():
                continue
            subject = _derive_subject(minutes) or "Reunião"
            for text in tasks.parse_action_items(minutes):
                tid = tasks.task_id(m.id, text)
                out.append(
                    {
                        "id": tid,
                        "meeting_id": m.id,
                        "subject": subject,
                        "started_at": m.started_at,
                        "text": text,
                        "done": bool(state.get(tid)),
                    }
                )
        return out

    def set_action_done(self, task_id: str, done: bool) -> dict:
        from core import tasks

        tasks.set_done(task_id, bool(done))
        return {"ok": True}

    # ---- Exportar / compartilhar a ata ----

    def get_minutes_text(self, meeting_id: str) -> dict:
        """Texto cru da ata (para copiar no clipboard pela UI)."""
        m = storage.get_meeting(meeting_id)
        if m is None:
            return {"error": "Reunião não encontrada."}
        d = Path(m.dir_path)
        return {"text": self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")}

    def export_minutes(self, meeting_id: str) -> dict:
        """Abre o diálogo 'Salvar como' e grava a ata (.md) no caminho escolhido."""
        m = storage.get_meeting(meeting_id)
        if m is None:
            return {"error": "Reunião não encontrada."}
        d = Path(m.dir_path)
        minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
        if not minutes.strip():
            return {"error": "Esta reunião não tem ata para exportar."}
        if self.window is None:
            return {"error": "Janela indisponível."}
        subject = _derive_subject(minutes) or "ata"
        safe = re.sub(r"[^\w\- ]", "", subject).strip()[:40] or "ata"
        result = self.window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=f"{safe}.md"
        )
        if not result:
            return {"cancelled": True}
        path = result if isinstance(result, str) else result[0]
        try:
            Path(path).write_text(minutes, encoding="utf-8")
            return {"ok": True, "path": path}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def send_webhook(self, meeting_id: str) -> dict:
        """Envia a ata para a URL de webhook configurada (Slack/Discord/Zapier)."""
        url = (read_raw().get("webhook_url") or "").strip()
        if not url:
            return {"error": "Configure a URL de webhook em Configuração."}
        m = storage.get_meeting(meeting_id)
        if m is None:
            return {"error": "Reunião não encontrada."}
        d = Path(m.dir_path)
        minutes = self._read_text(m.minutes_path) or self._read_text(d / "minutes.md")
        if not minutes.strip():
            return {"error": "Esta reunião não tem ata para enviar."}
        subject = _derive_subject(minutes) or "Ata da reunião"
        disc = minutes if len(minutes) <= 1800 else minutes[:1800] + "\n… (ata completa no app)"
        # Payload compatível com Slack ({text}) e Discord ({content}).
        payload = {"text": f"*{subject}*\n\n{minutes}", "content": f"**{subject}**\n\n{disc}"}
        try:
            import httpx

            r = httpx.post(url, json=payload, timeout=15)
            r.raise_for_status()
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Falha ao enviar: {e}"}

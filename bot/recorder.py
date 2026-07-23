"""Comandos slash do bot: /gravar e /parar.

O Pycord (2.8.x) grava o canal de voz e entrega o áudio decodificado por participante
via `PerUserPCMSink`. Salvamos uma faixa .wav por pessoa e disparamos o pipeline.
"""
from __future__ import annotations

import asyncio
from typing import Callable

import discord
from discord.ext import commands

from bot.pcmsink import PerUserPCMSink, dave_state_report, reset_decode_stats
from bot.pipeline import Pipeline
from core import storage


def _safe_name(name: str) -> str:
    """Nome de arquivo seguro a partir do nome de exibição do usuário."""
    keep = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()
    return keep.replace(" ", "_") or "participante"


# Etapas mostradas no Discord (o áudio já foi salvo quando o processamento começa).
_STEPS = [("transcribe", "✍️ Transcrevendo a fala"), ("generate", "🤖 Gerando a ata com a IA")]


def _render_steps(active: str) -> str:
    """Checklist do progresso para editar na mensagem do Discord."""
    idx = {k: i for i, (k, _) in enumerate(_STEPS)}
    ai = idx.get(active, len(_STEPS))  # "done" => todas concluídas
    lines = ["**Processando a ata**", "✅ 💾 Áudio salvo"]
    for i, (_k, label) in enumerate(_STEPS):
        mark = "✅" if (active == "done" or i < ai) else ("⏳" if i == ai else "▫️")
        lines.append(f"{mark} {label}")
    return "\n".join(lines)


class Recorder(commands.Cog):
    def __init__(
        self,
        bot: discord.Bot,
        pipeline: Pipeline,
        log: Callable[[str], None] | None = None,
        post_to_discord: bool = True,
    ):
        self.bot = bot
        self.pipeline = pipeline
        self.log = log or (lambda _msg: None)
        # Quando False, o bot não posta nada no canal (só salva + loga). Vem da config.
        self.post_to_discord = post_to_discord
        # Estado por servidor: guild_id -> (voice_client, sink, meeting)
        self.active: dict[
            int, tuple[discord.VoiceClient, PerUserPCMSink, storage.Meeting]
        ] = {}

    async def _connect_voice(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        """Conecta (ou reaproveita) o voice client e espera o handshake concluir.

        O `connect()` pode retornar antes de a conexão de voz estar realmente pronta;
        gravar nesse instante estoura "Not connected to voice channel". Então aqui a
        gente aguarda o `is_connected()` de verdade antes de devolver.
        """
        vc = channel.guild.voice_client
        if vc and vc.is_connected():
            if vc.channel != channel:
                await vc.move_to(channel)
        else:
            vc = await channel.connect(timeout=20.0, reconnect=True)

        for _ in range(50):  # até ~5s esperando o handshake de voz
            if vc.is_connected():
                break
            await asyncio.sleep(0.1)
        if not vc.is_connected():
            raise RuntimeError("a conexão de voz não ficou pronta a tempo")
        return vc

    @discord.slash_command(description="Entra no seu canal de voz e começa a gravar a reunião.")
    async def gravar(self, ctx: discord.ApplicationContext):
        if not ctx.author.voice:
            await ctx.respond("❌ Você precisa estar num canal de voz.", ephemeral=True)
            return
        if ctx.guild.id in self.active:
            await ctx.respond("⚠️ Já existe uma gravação em andamento neste servidor.", ephemeral=True)
            return

        # Confirma o comando já (o connect pode passar dos 3s do Discord).
        # Com o envio ao canal desligado, a resposta fica privada (ephemeral).
        await ctx.defer(ephemeral=not self.post_to_discord)

        channel = ctx.author.voice.channel
        try:
            vc = await self._connect_voice(channel)
        except Exception as e:  # noqa: BLE001 — reportar no chat em vez de morrer calado
            self.log(f"❌ Falha ao conectar no canal de voz: {e}")
            await ctx.respond(f"❌ Não consegui conectar ao canal de voz: `{e}`")
            return

        meeting = storage.create_meeting(ctx.guild.id, ctx.channel.id)
        reset_decode_stats()  # zera contadores de diagnóstico desta gravação
        sink = PerUserPCMSink()
        sink.vc = vc  # a 2.8.0 não chama sink.init(); o decoder precisa de sink.client
        self.active[ctx.guild.id] = (vc, sink, meeting)

        # Na 2.8.0 o callback pós-gravação recebe só a exceção e roda numa THREAD.
        # Agendamos o processamento (async) de volta no event loop via closure.
        loop = asyncio.get_running_loop()
        gid = ctx.guild.id

        def after_recording(exc: Exception | None) -> None:
            asyncio.run_coroutine_threadsafe(
                self._process(exc, ctx, gid, sink, vc, meeting.id), loop
            )

        try:
            vc.start_recording(sink, after_recording)
        except Exception as e:  # noqa: BLE001
            self.active.pop(ctx.guild.id, None)
            await vc.disconnect(force=True)
            self.log(f"❌ Falha ao iniciar a gravação: {e}")
            await ctx.respond(f"❌ Não consegui iniciar a gravação: `{e}`")
            return

        self.log(f"🔴 Gravação iniciada (reunião {meeting.id}) em '{channel.name}'.")
        self.log(f"🔐 {dave_state_report(vc)}")
        await ctx.respond(
            f"🔴 Gravando em **{channel.name}**. Use `/parar` para encerrar e gerar a ata."
        )

    @discord.slash_command(description="Encerra a gravação e gera a ata.")
    async def parar(self, ctx: discord.ApplicationContext):
        entry = self.active.get(ctx.guild.id)
        if not entry:
            # Sem gravação ativa: se o bot ficou preso no canal de voz, desconecta.
            vc = ctx.guild.voice_client
            if vc and vc.is_connected():
                await vc.disconnect(force=True)
                await ctx.respond("🔌 Não havia gravação ativa; desconectei o bot do canal de voz.")
            else:
                await ctx.respond("❌ Não há gravação em andamento.", ephemeral=True)
            return
        vc, _sink, _meeting = entry
        await ctx.defer(ephemeral=not self.post_to_discord)
        vc.stop_recording()  # dispara o after_recording -> _process
        await ctx.respond("⏳ Encerrando e processando a ata...")

    async def _process(
        self,
        exc: Exception | None,
        ctx: discord.ApplicationContext,
        gid: int,
        sink: PerUserPCMSink,
        vc: discord.VoiceClient,
        meeting_id: str,
    ):
        self.active.pop(gid, None)
        try:
            await vc.disconnect(force=True)
        except Exception:  # noqa: BLE001 — já pode estar desconectado
            pass

        if exc is not None:
            self.log(f"❌ Erro durante a gravação: {exc}")

        meeting = storage.get_meeting(meeting_id)
        if meeting is None:
            return

        # Salva uma faixa .wav por participante (PCM 48kHz estéreo 16-bit).
        def name_for(uid: int) -> str:
            member = ctx.guild.get_member(uid)
            return _safe_name(member.display_name if member else str(uid))

        total_bytes = sum(len(b) for b in sink.pcm.values())
        self.log(
            f"🎧 Áudio capturado: {total_bytes} bytes de {len(sink.pcm)} fonte(s)."
        )
        # Diagnóstico decisivo: pacotes recebidos/decodificados + pico de amplitude.
        # pico=0 com bytes>0 => áudio veio zerado (DAVE). falhou alto => não decodificou.
        self.log(f"🔬 Diagnóstico → {sink.signal_report(name_for)}")

        tracks = sink.save_wavs(meeting.dir, name_for)

        if not tracks:
            self.log("⚠️ Nenhum áudio capturado — ninguém falou?")
            if self.post_to_discord:
                await ctx.followup.send("⚠️ Nenhum áudio capturado — ninguém falou?")
            storage.update_meeting(meeting_id, status="error", ended_at=True)
            return

        self.log(f"📝 Processando reunião {meeting.id}: {len(tracks)} participante(s)...")
        # Só cria a mensagem-checklist no canal se for postar no Discord.
        status_msg = (
            await ctx.followup.send(_render_steps("transcribe"))
            if self.post_to_discord
            else None
        )

        # on_step roda em thread de trabalho -> editar a mensagem precisa voltar
        # ao event loop. Só edita quando muda de ETAPA (evita rate limit do Discord).
        loop = asyncio.get_running_loop()
        last_stage = {"k": "transcribe"}

        def on_step(key: str, detail: str = ""):
            self.log(f"… {key} {detail}".rstrip())
            if status_msg is None:
                return  # envio ao canal desligado: não há checklist para editar
            if key == last_stage["k"] and key != "done":
                return
            last_stage["k"] = key
            asyncio.run_coroutine_threadsafe(
                status_msg.edit(content=_render_steps(key)), loop
            )

        try:
            meeting = await self.pipeline.process(meeting, tracks, on_step=on_step)
        except Exception as e:  # noqa: BLE001 — reportar ao usuário no chat
            self.log(f"❌ Erro ao gerar a ata: {e}")
            if self.post_to_discord:
                await ctx.followup.send(f"❌ Erro ao gerar a ata: `{e}`")
            return

        self.log(f"✅ Ata da reunião {meeting.id} gerada.")

        minutes_text = (meeting.minutes_path and open(meeting.minutes_path, encoding="utf-8").read()) or ""
        if self.post_to_discord:
            await self._send_minutes(ctx, meeting, minutes_text)
        else:
            preview = minutes_text[:800] + ("…" if len(minutes_text) > 800 else "")
            self.log(
                f"📄 (envio ao canal desligado) Ata salva em: {meeting.minutes_path}\n"
                f"----- PRÉVIA -----\n{preview}"
            )

    async def _send_minutes(
        self, ctx: discord.ApplicationContext, meeting: storage.Meeting, minutes: str
    ):
        header = f"✅ **Ata da reunião** (`{meeting.id}`)\n\n"
        # Discord limita mensagens a 2000 caracteres; anexa o .md e manda um preview.
        file = discord.File(meeting.minutes_path, filename=f"ata_{meeting.id}.md")
        preview = minutes if len(minutes) <= 1800 else minutes[:1800] + "\n\n… (ata completa no arquivo anexo)"
        await ctx.followup.send(header + preview, file=file)

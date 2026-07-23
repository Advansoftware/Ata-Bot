"""Monta o bot do Discord. Usado tanto pela interface quanto pelo modo headless."""
from __future__ import annotations

from typing import Callable

import discord

from bot.pipeline import Pipeline
from bot.recorder import Recorder
from core.config import Config


def build_bot(cfg: Config, log: Callable[[str], None] | None = None) -> discord.Bot:
    log = log or (lambda _msg: None)

    intents = discord.Intents.default()
    intents.voice_states = True
    bot = discord.Bot(intents=intents)

    log("Carregando modelo de transcrição (primeira vez pode demorar)...")
    pipeline = Pipeline(cfg)
    bot.add_cog(Recorder(bot, pipeline, log, post_to_discord=cfg.post_to_discord))

    @bot.event
    async def on_ready():
        log(f"✅ Bot conectado como {bot.user}. Comandos: /gravar e /parar")

    return bot

"""Diagnóstico de conexão de voz — roda sozinho, sem precisar de /comando.

Loga com o token do settings.json, entra num canal de voz e mostra, com o log de
depuração do Discord no máximo, exatamente o que acontece no handshake de voz.

Uso:
    .venv/bin/python diag_voice.py
    .venv/bin/python diag_voice.py "Geral"     # nome do canal de voz (opcional)
"""
from __future__ import annotations

import asyncio
import logging
import sys

import discord

from core.config import Config

# Log de depuração do Discord no máximo -> mostra o handshake de voz e close codes.
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

cfg = Config.load()
wanted = sys.argv[1] if len(sys.argv) > 1 else None

# Python 3.14: precisa de um event loop no MainThread antes de criar o discord.Bot.
asyncio.set_event_loop(asyncio.new_event_loop())

intents = discord.Intents.default()
intents.voice_states = True
bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f"\n=== Conectado como {bot.user} ===")
    for g in bot.guilds:
        vcs = [c for c in g.channels if isinstance(c, discord.VoiceChannel)]
        print(f"Servidor: {g.name} — canais de voz: {[c.name for c in vcs]}")

    # Escolhe o canal: pelo nome passado, senão o primeiro que existir.
    channel = None
    for g in bot.guilds:
        for c in g.channels:
            if isinstance(c, discord.VoiceChannel):
                if wanted is None or c.name.lower() == wanted.lower():
                    channel = c
                    break
        if channel:
            break

    if channel is None:
        print("❌ Nenhum canal de voz encontrado.")
        await bot.close()
        return

    print(f"\n>>> Tentando conectar em '{channel.name}' (guild '{channel.guild.name}')...\n")
    try:
        vc = await channel.connect(timeout=30.0, reconnect=False)
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ connect() lançou exceção: {type(e).__name__}: {e}")
        await bot.close()
        return

    # Acompanha o is_connected() por 15s.
    for i in range(30):
        print(f"[{i*0.5:.1f}s] is_connected() = {vc.is_connected()}")
        if vc.is_connected():
            print("\n✅ CONECTOU DE VERDADE. Voz está pronta.")
            break
        await asyncio.sleep(0.5)
    else:
        print("\n❌ connect() retornou mas is_connected() nunca ficou True.")

    await asyncio.sleep(1)
    try:
        await vc.disconnect(force=True)
    except Exception:  # noqa: BLE001
        pass
    await bot.close()


bot.run(cfg.discord_token)

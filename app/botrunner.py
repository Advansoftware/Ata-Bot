"""Gerencia o ciclo de vida do bot do Discord numa thread separada.

A interface (thread principal) chama start()/stop(); o bot roda com seu próprio
event loop asyncio numa thread de fundo. Logs são enviados de volta via callback.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable

from bot.factory import build_bot
from core import storage
from core.config import Config


class BotRunner:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bot = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> str:
        if self._running:
            return "O bot já está rodando."

        cfg = Config.load()
        if not cfg.is_configured():
            msg = "⚠️ Configure o token do Discord e a chave do provedor antes de iniciar."
            self._log(msg)
            return msg

        self._running = True
        self._thread = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._thread.start()
        return "Iniciando o bot..."

    def _run(self, cfg: Config) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            storage.init_db()
            self._bot = build_bot(cfg, self._log)
            self._log("Conectando ao Discord...")
            self._loop.run_until_complete(self._bot.start(cfg.discord_token))
        except Exception as e:  # noqa: BLE001 — reportar na interface
            self._log(f"❌ Erro no bot: {e}")
        finally:
            self._running = False
            self._bot = None
            self._log("⏹️ Bot parado.")

    def stop(self) -> str:
        if not self._running or not self._bot or not self._loop:
            return "O bot não está rodando."
        self._log("Parando o bot...")
        asyncio.run_coroutine_threadsafe(self._bot.close(), self._loop)
        return "Parando o bot..."

"""Modo headless (sem interface):  python -m bot

Usa o settings.json já configurado pela interface. Útil para rodar num servidor.
Para a interface gráfica, use:  python -m app
"""
from __future__ import annotations

from bot.factory import build_bot
from core import storage
from core.config import Config


def main() -> None:
    cfg = Config.load()
    if not cfg.is_configured():
        raise SystemExit(
            "Configuração incompleta. Abra a interface (python -m app) e "
            "preencha o token do Discord e a chave do provedor."
        )
    storage.init_db()
    bot = build_bot(cfg, log=print)
    bot.run(cfg.discord_token)


if __name__ == "__main__":
    main()

"""Interface gráfica (app desktop nativo):  python -m app"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import webview

from app.api import Api

# Base dos recursos: dentro do bundle quando empacotado (PyInstaller), senão o
# diretório app/ do projeto. Assets vão em <base>/app/ (ver packaging/atabot.spec).
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys._MEIPASS) / "app"  # type: ignore[attr-defined]
else:
    APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
ICON_PNG = APP_DIR / "icon.png"
# Ícone do app (usado na janela/dock/barra de tarefas). .ico no Windows, .png nos demais.
ICON = APP_DIR / ("icon.ico" if os.name == "nt" else "icon.png")


def _set_linux_icon() -> None:
    """No Linux (GTK) o `icon=` do pywebview costuma ser ignorado.

    Definimos o ícone padrão das janelas GTK e o nome do programa diretamente —
    isso pega a barra de título, o Alt-Tab e a barra de tarefas na maioria dos
    ambientes (GNOME pode ainda usar o .desktop; veja o README).
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib, Gtk

        GLib.set_prgname("ata-bot")  # vira o WM_CLASS (casa com um .desktop, se houver)
        Gtk.Window.set_default_icon_from_file(str(ICON_PNG))
    except Exception:
        pass  # sem GTK/gi: segue sem ícone custom (não quebra o app)


def main() -> None:
    api = Api()
    window = webview.create_window(
        "Ata Bot — Reuniões do Discord",
        url=str(WEB_DIR / "index.html"),
        js_api=api,
        width=1180,
        height=820,
        min_size=(900, 640),
    )
    api.set_window(window)

    _set_linux_icon()

    # pywebview >= 5 aceita icon= no start(); versões antigas não — cai no fallback.
    try:
        webview.start(icon=str(ICON))
    except TypeError:
        webview.start()


if __name__ == "__main__":
    main()

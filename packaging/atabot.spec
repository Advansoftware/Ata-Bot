# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller — gera um app de verdade por SO.

Rode a partir da RAIZ do projeto (os scripts build.sh/build.bat fazem isso):
    pyinstaller --noconfirm packaging/atabot.spec

Saída:
  - Windows: dist/Ata Bot/Ata Bot.exe
  - Linux:   dist/Ata Bot/Ata Bot        (+ empacote em AppImage se quiser — README)
  - macOS:   dist/Ata Bot.app            (bundle nativo, com ícone e nome no Dock)

Importante: NÃO dá para cross-compilar. Rode o build em cada SO de destino.
"""
import os
import re
import sys

from PyInstaller.utils.hooks import collect_all

# Caminhos relativos num .spec são resolvidos a partir da pasta do spec (SPECPATH).
# Ancoramos tudo na RAIZ do projeto (pasta acima de packaging/).
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

# Versão vinda do CI (env ATABOT_VERSION, ex.: "1.2.0" ou "1.2.0-rc1"). Para o
# CFBundleShortVersionString do macOS só o x.y.z numérico é válido.
_RAW_VERSION = os.environ.get("ATABOT_VERSION", "0.0.0")
_m = re.match(r"(\d+\.\d+\.\d+)", _RAW_VERSION)
VERSION = _m.group(1) if _m else "0.0.0"

datas, binaries, hiddenimports = [], [], []

# Coleta libs/binários/submódulos das dependências pesadas (ffmpeg do PyAV, libs do
# ctranslate2, dados do faster-whisper, PortAudio do sounddevice, etc.).
for pkg in [
    "faster_whisper", "av", "ctranslate2", "sounddevice", "onnxruntime",
    "webview", "anthropic", "openai", "google.genai", "httpx",
    "huggingface_hub", "tokenizers",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:  # pacote ausente não deve quebrar o build
        print(f"[atabot.spec] aviso: collect_all({pkg}) falhou: {e}")

# Nossos assets: a interface web e os ícones (ficam em <bundle>/app/...).
datas += [
    (os.path.join(ROOT, "app", "web"), "app/web"),
    (os.path.join(ROOT, "app", "icon.png"), "app"),
    (os.path.join(ROOT, "app", "icon.ico"), "app"),
    (os.path.join(ROOT, "app", "icon.icns"), "app"),
]

icon = None
if sys.platform == "darwin":
    icon = os.path.join(ROOT, "app", "icon.icns")
elif sys.platform == "win32":
    icon = os.path.join(ROOT, "app", "icon.ico")

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ata Bot",
    debug=False,
    strip=False,
    upx=False,
    console=False,       # sem janela de terminal (GUI)
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Ata Bot",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Ata Bot.app",
        icon=os.path.join(ROOT, "app", "icon.icns"),
        bundle_identifier="com.atabot.app",
        info_plist={
            "CFBundleName": "Ata Bot",
            "CFBundleDisplayName": "Ata Bot",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            # Permissões exigidas no macOS:
            "NSMicrophoneUsageDescription": "O Ata Bot usa o microfone para o teste de transcrição.",
        },
    )

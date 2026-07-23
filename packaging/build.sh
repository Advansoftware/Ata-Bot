#!/usr/bin/env bash
# Empacota o app (macOS/Linux). Rode DENTRO do venv do projeto, no SO de destino.
#   macOS  -> dist/Ata Bot.app
#   Linux  -> dist/Ata Bot/Ata Bot   (veja o README para AppImage + .desktop)
set -e
cd "$(dirname "$0")/.."

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install --upgrade pyinstaller
rm -rf build "dist"
pyinstaller --noconfirm packaging/atabot.spec

echo ""
if [ "$(uname)" = "Darwin" ]; then
  echo "✅ Pronto: dist/Ata Bot.app  (arraste para /Applications)"
else
  echo "✅ Pronto: dist/Ata Bot/     (execute ./dist/Ata\\ Bot/Ata\\ Bot)"
  echo "   Para instalar com ícone no menu, veja packaging/ata-bot.desktop e o README."
fi

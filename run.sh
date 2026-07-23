#!/usr/bin/env bash
# Abre o programa (janela nativa). Uso:  ./run.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Ambiente não encontrado. Rode ./setup.sh primeiro."
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m app

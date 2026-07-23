#!/usr/bin/env bash
# Setup para Linux e macOS. Uso:  ./setup.sh
set -e
cd "$(dirname "$0")"

# Escolhe um Python (prefere 3.12, que tem wheels de todas as deps).
PY=""
for c in python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "❌ Python não encontrado. Instale o Python 3.11 ou 3.12."
  exit 1
fi
echo "▶ Usando $($PY --version)"

# No Linux, duas libs de SISTEMA são necessárias (o pip não as instala, porque
# fazem parte do sistema gráfico/de áudio do SO):
#   - WebKitGTK  -> janela nativa (pywebview)
#   - PortAudio  -> captura do microfone (sounddevice, teste sem Discord)
# No Windows/macOS isso já vem com o SO — nada a fazer.
if [ "$(uname)" = "Linux" ]; then
  NEED_WEBKIT=0
  NEED_PORTAUDIO=0
  "$PY" -c "import gi" >/dev/null 2>&1 || NEED_WEBKIT=1
  ldconfig -p 2>/dev/null | grep -qi 'libportaudio' || NEED_PORTAUDIO=1

  if [ "$NEED_WEBKIT" = 1 ] || [ "$NEED_PORTAUDIO" = 1 ]; then
    # Descobre o gerenciador de pacotes e monta o comando de instalação.
    PKG_CMD=""
    if command -v apt-get >/dev/null 2>&1; then
      PKGS=""; [ "$NEED_WEBKIT" = 1 ] && PKGS="python3-gi gir1.2-webkit2-4.1 python3-gi-cairo"
      [ "$NEED_PORTAUDIO" = 1 ] && PKGS="$PKGS libportaudio2"
      PKG_CMD="sudo apt-get install -y $PKGS"
    elif command -v dnf >/dev/null 2>&1; then
      PKGS=""; [ "$NEED_WEBKIT" = 1 ] && PKGS="python3-gobject webkit2gtk4.1"
      [ "$NEED_PORTAUDIO" = 1 ] && PKGS="$PKGS portaudio"
      PKG_CMD="sudo dnf install -y $PKGS"
    elif command -v pacman >/dev/null 2>&1; then
      PKGS=""; [ "$NEED_WEBKIT" = 1 ] && PKGS="python-gobject webkit2gtk-4.1"
      [ "$NEED_PORTAUDIO" = 1 ] && PKGS="$PKGS portaudio"
      PKG_CMD="sudo pacman -S --noconfirm $PKGS"
    elif command -v zypper >/dev/null 2>&1; then
      PKGS=""; [ "$NEED_WEBKIT" = 1 ] && PKGS="python3-gobject webkit2gtk3"
      [ "$NEED_PORTAUDIO" = 1 ] && PKGS="$PKGS portaudio"
      PKG_CMD="sudo zypper install -y $PKGS"
    fi

    NAMES=""; [ "$NEED_WEBKIT" = 1 ] && NAMES="WebKitGTK"
    [ "$NEED_PORTAUDIO" = 1 ] && NAMES="$NAMES PortAudio"
    echo "⚠️  Faltam libs de sistema no Linux:$NAMES (o pip não instala essas)."

    if [ -n "$PKG_CMD" ]; then
      echo "    Posso instalar pra você com:  $PKG_CMD"
      printf "    Instalar agora? [S/n] "
      read -r ANS </dev/tty || ANS="n"
      case "$ANS" in
        [Nn]*) echo "    Ok, pulando. Rode o comando acima antes de usar o app." ;;
        *)     echo "▶ Instalando libs de sistema..."; eval "$PKG_CMD" || \
                 echo "    ⚠️  Falhou. Rode manualmente:  $PKG_CMD" ;;
      esac
    else
      echo "    Não reconheci seu gerenciador de pacotes. Instale manualmente:"
      echo "    Debian/Ubuntu:  sudo apt install python3-gi gir1.2-webkit2-4.1 python3-gi-cairo libportaudio2"
      echo "    Fedora:         sudo dnf install python3-gobject webkit2gtk4.1 portaudio"
      echo "    Arch:           sudo pacman -S python-gobject webkit2gtk-4.1 portaudio"
    fi
    echo ""
  fi
fi

echo "▶ Criando ambiente virtual (.venv)..."
# --system-site-packages deixa o venv enxergar o python3-gi do sistema (Linux).
if [ "$(uname)" = "Linux" ]; then
  "$PY" -m venv --system-site-packages .venv
else
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "▶ Instalando dependências (a primeira vez baixa o modelo de voz depois, no 1º uso)..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo ""
echo "✅ Pronto! Para abrir o programa:  ./run.sh"
echo "   Na janela: cole o token do Discord, escolha o provedor + chave, e clique em Iniciar bot."

#!/usr/bin/env bash
# Integra o Ata Bot ao Linux: registra o app no menu com o ícone correto.
#
# Por que isso é preciso: um binário ELF cru (dist/Ata Bot/Ata Bot) SEMPRE aparece
# com ícone genérico no gerenciador de arquivos — o SO não lê ícone de dentro do
# executável. O ícone bonito aparece no menu de apps e na dock quando existe um
# arquivo .desktop instalado apontando para o ícone. É o que este script faz.
#
# Uso (a partir da RAIZ do projeto, depois de rodar ./packaging/build.sh):
#     ./packaging/install-linux.sh
# ou apontando para outra pasta do app:
#     ./packaging/install-linux.sh "/opt/ata-bot"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Pasta do app empacotado (contém o executável "Ata Bot" e _internal/).
APP_DIR="${1:-$ROOT/dist/Ata Bot}"
EXE="$APP_DIR/Ata Bot"

if [[ ! -x "$EXE" ]]; then
  echo "✗ Não encontrei o executável em: $EXE"
  echo "  Rode primeiro:  ./packaging/build.sh"
  echo "  Ou passe o caminho do app:  ./packaging/install-linux.sh /caminho/para/Ata\\ Bot"
  exit 1
fi

# Ícone: preferimos o do bundle; senão o do projeto.
ICON_SRC="$APP_DIR/_internal/app/icon.png"
[[ -f "$ICON_SRC" ]] || ICON_SRC="$ROOT/app/icon.png"

APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
DESKTOP_FILE="$APPS_DIR/ata-bot.desktop"

mkdir -p "$APPS_DIR" "$ICON_DIR"

# Instala o ícone com um nome estável no tema de ícones do usuário.
cp -f "$ICON_SRC" "$ICON_DIR/ata-bot.png"

# Escreve o .desktop com os caminhos absolutos reais desta máquina.
# StartupWMClass=ata-bot casa com GLib.set_prgname("ata-bot") do app -> a janela
# em execução também herda o ícone (barra de título, Alt-Tab, dock).
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Ata Bot
Comment=Grava reuniões do Discord, transcreve e gera a ata
Exec="$EXE"
Icon=ata-bot
Terminal=false
Categories=AudioVideo;Utility;
StartupWMClass=ata-bot
EOF

chmod +x "$DESKTOP_FILE"

# Atualiza os caches (silencioso se as ferramentas não existirem).
update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

echo "✓ Ata Bot instalado no menu de aplicativos."
echo "  Lançador: $DESKTOP_FILE"
echo "  Ícone:    $ICON_DIR/ata-bot.png"
echo
echo "Abra pelo menu de aplicativos (procure por 'Ata Bot') para ver o ícone."
echo "Se não aparecer na hora, faça logout/login (o GNOME recarrega o menu)."
echo
echo "Para remover:  rm '$DESKTOP_FILE' '$ICON_DIR/ata-bot.png'"

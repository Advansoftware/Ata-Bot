# 🎙️ Ata Bot — reuniões do Discord

Bot que **grava** uma reunião num canal de voz do Discord, **transcreve** localmente
e **gera a ata** automaticamente (estilo Gemini/Meet), postando de volta no chat.

Tem um **app desktop nativo** (janela própria, roda no Windows, macOS e Linux) para
configurar tudo por formulário e iniciar/parar o bot — sem editar arquivos à mão.

## Como funciona

1. Você abre o programa (janela nativa) e configura: token do Discord, provedor da
   ata + chave, idioma e o modelo do Whisper (com botão **⬇ Baixar** e barra de
   progresso; fica salvo em `data/models/`).
2. No Discord: `/gravar` faz o bot entrar no canal de voz; `/parar` encerra.
3. A transcrição roda **localmente** (faster-whisper), com áudio separado por
   participante — a ata sai já sabendo quem falou o quê.
4. A ata é gerada pelo provedor escolhido e postada no chat (+ arquivo `.md`).

## Provedores de ata (escolha na interface)

| Provedor | Onde roda | Custo | Observação |
|---|---|---|---|
| **Anthropic — Claude** | nuvem (API) | centavos/reunião | alta qualidade |
| **OpenAI — ChatGPT** | nuvem (API) | centavos/reunião | alta qualidade |
| **Google — Gemini** | nuvem (API) | centavos/reunião | alta qualidade |
| **Ollama** | 100% local | zero | precisa de máquina boa; nada sai do PC |

> A gravação e a transcrição são sempre **locais**. Só o texto da transcrição vai para
> o provedor de nuvem (quando você não usa o Ollama).

## Instalação

Recomendado: **Python 3.11 ou 3.12** (o 3.14 é muito novo e algumas libs ainda não
têm pacote pronto).

### Windows
1. Instale o Python de [python.org](https://www.python.org/downloads/) marcando
   **"Add Python to PATH"**.
2. Baixe/clone este projeto, entre na pasta e dê **duplo-clique em `setup.bat`**.
3. Para abrir: **duplo-clique em `run.bat`**.

### macOS
```bash
./setup.sh
./run.sh
```

### Linux
```bash
./setup.sh
./run.sh
```
No Windows e no macOS tudo vem via `pip` — nada externo. **Só no Linux** duas libs
de sistema são necessárias (o `pip` não as instala, porque fazem parte do sistema
gráfico/de áudio do SO): **WebKitGTK** (janela nativa) e **PortAudio** (microfone do
teste). Você **não precisa instalá-las à mão**: o `setup.sh` detecta a sua distro e
se oferece para instalá-las automaticamente. Se preferir fazer manualmente:
```bash
# Debian/Ubuntu
sudo apt install python3-gi gir1.2-webkit2-4.1 python3-gi-cairo libportaudio2
# Fedora:  sudo dnf install python3-gobject webkit2gtk4.1 portaudio
# Arch:    sudo pacman -S python-gobject webkit2gtk-4.1 portaudio
```

> **ffmpeg?** Não precisa instalar no sistema — o `faster-whisper` já traz o
> necessário via pip, e o bot grava WAV puro.

## Criando o bot no Discord (uma vez)

1. [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Aba **Bot** → **Reset Token** → copie (é o que vai na interface).
3. Ainda em **Bot**, ligue **Server Members Intent** (para pegar o nome de quem falou).
4. Aba **OAuth2 → URL Generator**: escopos `bot` + `applications.commands`; permissões
   `Connect`, `Speak`, `Send Messages`. Abra a URL gerada e adicione o bot ao seu servidor.

## Uso

- `/gravar` — o bot entra no seu canal de voz e começa a gravar.
- `/parar` — encerra, transcreve, gera a ata e posta no chat.

Cada reunião vira uma subpasta `<id>/` com os áudios (um `.wav` por participante),
`transcript.txt` e `minutes.md`. A **pasta de destino é escolhida na interface**
(botão "Escolher…"); o padrão é `data/meetings/`. O índice fica em `data/meetings.db`
e guarda o caminho de cada reunião, então mudar a pasta não perde as antigas.

## Estrutura do projeto

```
core/           # lógica reutilizável, independente do Discord
  config.py       # settings.json (token, provedor, chaves, idioma)
  storage.py      # SQLite + arquivos das reuniões
  transcriber.py  # faster-whisper (transcrição por participante)
  minutes/        # provedores de ata: claude, openai, gemini, ollama (interface comum)
bot/            # camada do Discord
  recorder.py     # comandos /gravar e /parar + captura de áudio
  pipeline.py     # transcrever -> gerar ata -> salvar
  factory.py      # monta o bot
app/            # app desktop nativo (pywebview)
  web/index.html  # a interface (HTML/CSS/JS)
  api.py          # ponte Python <-> UI
  botrunner.py    # inicia/para o bot em thread própria
```

O `core/` não depende do Discord de propósito: o painel/relatórios futuros
reaproveitam a transcrição e a geração de ata direto dele.

## Empacotar como app de verdade (.app / .exe / binário)

Dá para gerar um aplicativo nativo (com ícone e nome próprios no Dock/barra de
tarefas) usando o **PyInstaller**. O empacotamento é **por sistema** — não dá para
cross-compilar; rode o build **no próprio SO de destino**, dentro do venv do projeto.

```bash
pip install -r requirements-build.txt
# macOS / Linux:
./packaging/build.sh
# Windows:
packaging\build.bat
```

Saída em `dist/`:
- **macOS** → `dist/Ata Bot.app` (arraste para `/Applications`). O ícone e o nome já
  vêm do bundle; na 1ª gravação o macOS pede permissão de microfone.
- **Windows** → `dist/Ata Bot/Ata Bot.exe` (precisa do WebView2 runtime — já vem no
  Windows 10/11 atualizado). Para um instalador único, use o Inno Setup sobre a pasta.
- **Linux** → `dist/Ata Bot/Ata Bot`. Continua precisando das libs de sistema
  (WebKitGTK e PortAudio). **Para o ícone no menu de aplicativos e na dock**, rode:
  ```bash
  ./packaging/install-linux.sh          # usa dist/Ata Bot; ou passe outro caminho
  ```
  Isso registra um `.desktop` e o ícone (`~/.local/share/applications/` +
  `~/.local/share/icons/`). Depois abra pelo **menu de aplicativos** (procure por
  "Ata Bot") — aí sim o ícone aparece. Observação honesta: o **binário em si, visto
  no gerenciador de arquivos, sempre mostra o ícone genérico de "executável"** — isso
  é do sistema, não dá para mudar; o ícone do app aparece na janela em execução e no
  menu. Para um único arquivo executável, empacote a pasta `dist/Ata Bot/` como
  **AppImage** (ferramenta `appimagetool`).

> No app empacotado, as configurações e os modelos ficam numa pasta do usuário
> (macOS: `~/Library/Application Support/AtaBot`; Windows: `%APPDATA%\AtaBot`;
> Linux: `~/.local/share/ata-bot`), não dentro do bundle.

## Rodar sem interface (opcional, ex.: servidor)

Depois de configurar uma vez pela interface (gera o `data/settings.json`):
```bash
python -m bot
```

## Privacidade

- `data/` e as chaves (`settings.json`) ficam **fora do git** (`.gitignore`).
- Com Ollama, nada sai da máquina. Com provedores de nuvem, só o texto da
  transcrição é enviado para gerar a ata.

# 🎙️ Ata Bot — reuniões do Discord

[![Licença: MIT](https://img.shields.io/badge/Licen%C3%A7a-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Plataformas](https://img.shields.io/badge/SO-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#instala%C3%A7%C3%A3o)
[![PRs bem-vindos](https://img.shields.io/badge/PRs-bem--vindos-brightgreen.svg)](CONTRIBUTING.md)

Bot **open source** que **grava** uma reunião num canal de voz do Discord,
**transcreve** localmente e **gera a ata** automaticamente (estilo Gemini/Meet),
postando de volta no chat.

Tem um **app desktop nativo** (janela própria, roda no Windows, macOS e Linux) para
configurar tudo por formulário e iniciar/parar o bot — sem editar arquivos à mão.

> Gravação e transcrição rodam **100% na sua máquina**. Só o texto da transcrição
> vai para o provedor de nuvem escolhido — e, com o Ollama, nada sai do PC.

## Como funciona

1. Você abre o programa (janela nativa) e configura: token do Discord, provedor da
   ata + chave, idioma e o modelo do Whisper (com botão **⬇ Baixar** e barra de
   progresso; fica salvo em `data/models/`).
2. No Discord: `/gravar` faz o bot entrar no canal de voz; `/parar` encerra.
3. A transcrição roda **localmente** (faster-whisper), com áudio separado por
   participante — a ata sai já sabendo quem falou o quê.
4. A ata é gerada pelo provedor escolhido e postada no chat (+ arquivo `.md`).
5. Tudo fica no **dashboard "Reuniões"** do próprio app: cada reunião vira um card
   (assunto, data e hora); ao abrir, você vê a **ata formatada**, a **transcrição**
   e um **player** para ouvir o áudio de cada participante. Enquanto uma reunião
   ainda processa, o card mostra o progresso por etapa (transcrevendo → gerando a ata).

Além disso, o app tem:

- **💬 Chat com as reuniões** — pergunte em linguagem natural sobre todo o histórico
  (*"quais foram as decisões da semana?"*). As respostas **citam a reunião e o
  momento exato**; clicar na citação abre a reunião e **toca o áudio naquele ponto**.
  Também há um **balão de chat dentro de cada reunião** para perguntar só sobre ela.
- **🗣️ Transcrição sincronizada** — clique em qualquer fala e o player pula para
  aquele instante; a linha que está tocando fica destacada.
- **🔎 Busca global** — procure um termo em assuntos, transcrições e atas.
- **✅ Tarefas** — os itens de ação de todas as atas reunidos numa lista, com
  estado de concluído que fica salvo.
- **Compartilhar a ata** — copiar, exportar `.md` ou enviar por **webhook**
  (Slack/Discord/Zapier).
- **📦 Importar/exportar reuniões** — empacote uma reunião (ou todas) num arquivo
  `.atabot` com **tudo** (áudio, transcrição, ata e índice do chat) e importe em
  outro PC com o app: a outra pessoa passa a ter exatamente o que você gerou.

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

Primeiro, clone o repositório:
```bash
git clone https://github.com/Advansoftware/Ata-Bot.git
cd Ata-Bot
```

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
  web/index.html  # a interface (HTML/CSS/JS): config, teste, log e dashboard de reuniões
  api.py          # ponte Python <-> UI (config, modelos, teste e listagem de reuniões)
  botrunner.py    # inicia/para o bot em thread própria
  audioserver.py  # servidor HTTP local (só localhost) que serve os .wav para o player
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

### Build automatizado (CI) — as três plataformas de uma vez

Como não dá para cross-compilar, o jeito prático de gerar o app para os três
sistemas (inclusive **macOS sem ter um Mac**) é o CI. Este repositório já traz um
workflow do **GitHub Actions** em [`.github/workflows/build.yml`](.github/workflows/build.yml)
que builda em `ubuntu-latest`, `windows-latest` e `macos-latest`:

- **Rodar sob demanda:** aba **Actions** → *Build & Release* → **Run workflow**.
  Ao terminar, baixe os pacotes em **Artifacts**.
- **Publicar uma versão:** crie e envie uma tag semver. O workflow builda as três
  plataformas e publica uma **Release** com os pacotes **versionados**, um
  `checksums.txt` (SHA-256) e as notas geradas automaticamente ("What's Changed"):
  ```bash
  git tag -a v1.0.0 -m "v1.0.0" && git push origin v1.0.0
  ```
  Tags com sufixo (`v1.0.0-rc1`, `v1.2.0-beta`) são publicadas como **pré-release**.
  A versão da tag é embutida no app (ex.: no *Sobre* do macOS).

Saída por plataforma: `Ata-Bot-<versão>-linux-x86_64.tar.gz`,
`Ata-Bot-<versão>-windows-x64.zip` e `Ata-Bot-<versão>-macOS-arm64.zip` (Apple
Silicon). Runners `macos-latest` são gratuitos em repositório público. O app do
macOS não é assinado, então na 1ª vez abra com **clique-direito → Abrir**
(Gatekeeper). O histórico de versões fica no [CHANGELOG.md](CHANGELOG.md).

## Rodar sem interface (opcional, ex.: servidor)

Depois de configurar uma vez pela interface (gera o `data/settings.json`):
```bash
python -m bot
```

Prefere configurar na mão? Copie o exemplo e preencha suas chaves:
```bash
mkdir -p data && cp settings.example.json data/settings.json
# edite data/settings.json com o token do Discord e a chave do provedor
```

## Privacidade

- `data/` e as chaves (`settings.json`) ficam **fora do git** (`.gitignore`).
- Com Ollama, nada sai da máquina. Com provedores de nuvem, só o texto da
  transcrição é enviado para gerar a ata.

## Contribuindo

Contribuições são muito bem-vindas! Veja o [CONTRIBUTING.md](CONTRIBUTING.md) para
preparar o ambiente, o padrão de código e como enviar um Pull Request. Bugs e
sugestões podem ir direto nas [issues](https://github.com/Advansoftware/Ata-Bot/issues).

## Licença

Distribuído sob a **Licença MIT** — use, modifique e distribua à vontade, inclusive
comercialmente, mantendo o aviso de copyright. Veja o arquivo [LICENSE](LICENSE).

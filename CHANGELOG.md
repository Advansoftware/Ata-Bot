# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- **Chat com as reuniões**: pergunte à IA sobre todo o histórico (ou sobre uma
  reunião específica, via balão de chat na tela da reunião). As respostas citam a
  reunião e o momento exato — clicar leva ao ponto e toca o áudio.
- **Transcrição sincronizada com o áudio**: clicar numa fala posiciona o player
  naquele instante; a linha em reprodução fica destacada.
- **Busca global** por assunto, transcrição e ata.
- **Tarefas**: itens de ação de todas as atas consolidados, com estado de
  concluído persistido (`data/tasks_state.json`).
- **Compartilhar a ata**: copiar, exportar `.md` e enviar por webhook
  (Slack/Discord/Zapier); campo `webhook_url` na configuração.

### Alterado
- O pipeline salva `transcript.txt` assim que a transcrição termina (antes da ata),
  o que preserva a transcrição mesmo se a geração da ata falhar.

## [1.0.0] - 2026-07-23

Primeira versão pública.

### Adicionado
- Gravação nativa de reuniões em canais de voz do Discord (`/gravar` e `/parar`),
  com áudio separado por participante.
- Transcrição local com faster-whisper (Whisper), em CPU ou GPU.
- Geração automática da ata com provedor à escolha: Claude, OpenAI, Gemini ou
  Ollama (100% local).
- App desktop nativo (pywebview) para configurar tudo por formulário.
- **Dashboard de reuniões** no app: cards por assunto e data/hora, com progresso
  por etapa enquanto processa; tela de detalhe com a ata formatada, a transcrição
  e um player de áudio por participante (play/pause, seek, velocidade).
- Servidor HTTP local (`app/audioserver.py`) para tocar os áudios no player.
- Build automatizado (GitHub Actions) para Windows, macOS e Linux, com Release
  versionada, pacotes por plataforma e checksums SHA-256.

### Corrigido
- Recepção de voz E2EE (DAVE) da py-cord 2.8.0 (bug upstream #3139): decriptação
  na ordem correta com fallback por membro do grupo, sem o corte extra do
  resultado, e jitter buffer sem-perdas para gravação. Contorno em `bot/pcmsink.py`.

[Não lançado]: https://github.com/Advansoftware/Ata-Bot/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Advansoftware/Ata-Bot/releases/tag/v1.0.0

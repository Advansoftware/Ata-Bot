# Contribuindo com o Ata Bot

Obrigado pelo interesse! Contribuições são muito bem-vindas — código, documentação,
tradução, testes ou só relatar um bug.

## Como reportar um problema

Abra uma [issue](https://github.com/Advansoftware/Ata-Bot/issues) descrevendo:

- o que você esperava e o que aconteceu;
- seu sistema operacional e a versão do Python (`python --version`);
- se for erro de execução, o log da janela do app (aba **Log**) ou do terminal.

## Preparando o ambiente

```bash
git clone git@github.com:Advansoftware/Ata-Bot.git
cd Ata-Bot
./setup.sh          # cria o .venv e instala tudo (Windows: setup.bat)
./run.sh            # abre o app
```

O código é organizado em três camadas (veja **Estrutura do projeto** no README):

- `core/` — lógica pura, sem Discord (config, storage, transcrição, provedores de ata);
- `bot/` — a camada do Discord (comandos, captura de áudio, pipeline);
- `app/` — o app desktop nativo (pywebview + HTML/JS).

## Enviando um Pull Request

1. Faça um fork e crie uma branch a partir da `main` (`git checkout -b minha-melhoria`).
2. Mantenha o estilo do código existente (nomes e comentários em português combinam
   com o resto do projeto).
3. **Nunca** comite segredos: `data/`, `settings.json`, chaves de API e o `.venv/`
   já estão no `.gitignore` — confira antes de commitar.
4. Descreva no PR o que mudou e por quê. Se corrigir um bug, diga como reproduzi-lo.

## Áreas que precisam de ajuda

- Empacotamento e instaladores (AppImage no Linux, Inno Setup no Windows).
- Novos provedores de ata e idiomas de transcrição.
- Testes automatizados para o `core/`.

Ao contribuir, você concorda que sua contribuição seja licenciada sob a
[Licença MIT](LICENSE) do projeto.

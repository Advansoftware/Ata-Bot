@echo off
REM Abre o programa (janela nativa). Duplo-clique ou rode: run.bat
cd /d "%~dp0"
if not exist ".venv" (
  echo Ambiente nao encontrado. Rode setup.bat primeiro.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m app

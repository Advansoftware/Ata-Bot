@echo off
REM Setup para Windows. Duplo-clique ou rode:  setup.bat
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo [ERRO] Python nao encontrado. Instale o Python 3.12 de python.org
    echo         e marque "Add Python to PATH" na instalacao.
    pause
    exit /b 1
  )
)

echo Criando ambiente virtual (.venv)...
%PY% -m venv .venv
call .venv\Scripts\activate.bat

echo Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Pronto! Para abrir o programa: run.bat
echo Na janela: cole o token do Discord, escolha o provedor + chave, e clique em Iniciar bot.
pause

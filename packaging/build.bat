@echo off
REM Empacota o app no Windows -> dist\Ata Bot\Ata Bot.exe
REM Rode dentro do venv do projeto (setup.bat cria o .venv).
cd /d "%~dp0\.."

if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pyinstaller
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm packaging\atabot.spec

echo.
echo ✅ Pronto: dist\Ata Bot\Ata Bot.exe
echo    (para um instalador .exe único, veja o README - Inno Setup)
pause

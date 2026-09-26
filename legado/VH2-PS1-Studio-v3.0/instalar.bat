@echo off
cd /d "%~dp0"
py -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Instalacao concluida. Execute iniciar.bat
pause

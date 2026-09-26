@echo off
REM Chay TikTok Video Studio tren Windows
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -m app %*
pause

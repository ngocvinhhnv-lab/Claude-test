@echo off
REM Chay TikTok Video Studio tren Windows
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where python >nul 2>nul || (echo Chua cai Python. Xem buoc 1 trong huong dan. & pause & exit /b 1)
where ffmpeg >nul 2>nul || echo Canh bao: chua thay ffmpeg. Xem buoc 2 trong huong dan.
if not exist .venv (
  echo Lan dau chay: dang cai dat, mat khoang 2-5 phut...
  python -m venv .venv || (echo Loi tao moi truong Python & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt || (echo Loi cai thu vien, kiem tra mang Internet & pause & exit /b 1)
REM yt-dlp can cap nhat thuong xuyen de tai duoc video TikTok moi
pip install -q -U --pre --no-deps yt-dlp >nul 2>nul
echo.
echo App dang chay. GIU CUA SO NAY MO trong luc dung app. Dong cua so = tat app.
python -m app %*
pause

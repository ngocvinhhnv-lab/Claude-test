@echo off
REM Chay TikTok Video Studio tren Windows
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where python >nul 2>nul || (echo Chua cai Python. Xem buoc 1 trong huong dan. & pause & exit /b 1)
python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" || echo Canh bao: nen dung Python 3.12 hoac 3.13. Ban Python khac co the loi khi cai thu vien.
where ffmpeg >nul 2>nul || echo Canh bao: chua thay ffmpeg. Xem buoc 2 trong huong dan.
if not exist .venv (
  echo Lan dau chay: dang cai dat, mat khoang 2-5 phut...
  python -m venv .venv || (echo Loi tao moi truong Python & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt || (echo Loi cai thu vien, kiem tra mang Internet & pause & exit /b 1)
REM Cac thu vien sau hay doi, cap nhat moi lan mo. Loi o day khong chan app (chi mat tinh nang dan link / doc giong Edge)
pip install -q "yt-dlp[default,curl-cffi]" >nul 2>nul || pip install -q yt-dlp >nul 2>nul
pip install -q -U --pre --no-deps yt-dlp >nul 2>nul
pip install -q -U edge-tts >nul 2>nul
echo.
title TikTok Video Studio - GIU CUA SO NAY MO
echo App dang chay. GIU CUA SO NAY MO trong luc dung app. Dong cua so = tat app.
echo Neu trinh duyet bao "Failed to fetch": cua so nay da bi dong hoac app da dung. Mo lai chay_app.bat.
python -m app %*
echo.
echo App da dung. Neu co dong chu do o tren, chup man hinh gui nguoi ho tro. Mo lai chay_app.bat de chay tiep.
pause

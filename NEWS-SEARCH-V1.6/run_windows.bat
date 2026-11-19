@echo off
title NEWS SEARCH V1.6
cd /d "%~dp0"
set "PY=py"
where py >nul 2>nul || set "PY=python"
if not exist ".venv" (
  echo Membuat virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Python tidak ditemukan. Install Python 3.10 atau lebih baru.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate
pip install -q -r requirements.txt
echo.
echo NEWS SEARCH berjalan. Buka browser di http://127.0.0.1:8001
echo Tekan CTRL+C untuk menghentikan.
python -m uvicorn app:app --host 127.0.0.1 --port 8001
pause

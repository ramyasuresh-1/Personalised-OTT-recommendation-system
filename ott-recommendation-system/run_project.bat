@echo off
title AURA OTT Recommender Launcher
echo ==========================================================
echo       AURA OTT RECOMMENDATION & MLOPS LAUNCHER
echo ==========================================================
echo.
echo [1/2] Opening Frontend Web UI in default browser...
start "" "%~dp0frontend\index.html"

echo.
echo [2/2] Launching Backend FastAPI Server...
cd /d "%~dp0backend"
call venv\Scripts\activate
uvicorn app.main:app --port 8000
pause

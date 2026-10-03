@echo off
setlocal
cd /d "%~dp0"
echo CutPilot AI start ho raha hai...
echo.

REM ---- Backend (API :8000) ----
if not exist "backend\.venv" (
  echo [ERROR] Pehle SETUP_WINDOWS.bat chalao.
  pause
  exit /b 1
)
start "CutPilot API :8000" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM ---- Frontend (Web :3000) ----
if not exist "frontend\node_modules" (
  echo [ERROR] Pehle SETUP_WINDOWS.bat chalao.
  pause
  exit /b 1
)
start "CutPilot Web :3000" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo Dono windows khul gayi hain. 15-20 second intezar karo...
timeout /t 18 /nobreak >nul
start http://localhost:3000
echo.
echo Browser mein http://localhost:3000 khul gaya hoga.
echo Login: demo@cutpilot.ai / DemoPass123!
echo.
echo Band karne ke liye dono cmd windows mein Ctrl+C dabao.
pause

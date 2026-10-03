@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo  CutPilot AI - Windows Setup (Docker ki zaroorat nahi)
echo ================================================
echo.

REM ---- 1. Python check ----
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python nahi mila.
  echo Install karo:  winget install Python.Python.3.12
  echo Phir terminal band karke dobara kholo aur ye file dobara chalao.
  pause
  exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

REM ---- 2. Node check ----
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js nahi mila.
  echo Install karo:  winget install OpenJS.NodeJS.LTS
  echo Phir terminal band karke dobara kholo aur ye file dobara chalao.
  pause
  exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do set NODEVER=%%v
echo [OK] Node %NODEVER%

REM ---- 3. ffmpeg check ----
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [ERROR] ffmpeg nahi mila.
  echo Install karo:  winget install Gyan.FFmpeg
  echo Phir terminal band karke dobara kholo aur ye file dobara chalao.
  pause
  exit /b 1
)
echo [OK] ffmpeg mil gaya

echo.
echo ---- Backend setup (pehli dafa 10-30 min lag sakte hain) ----
cd backend
if not exist ".venv" (
  echo Virtual environment bana raha hoon...
  python -m venv .venv
  if errorlevel 1 ( echo [ERROR] venv nahi bana. & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
echo Python packages install ho rahe hain (torch/faster-whisper bara hai, sabar rakho)...
python -m pip install --upgrade pip >nul
pip install -r requirements-windows.txt
if errorlevel 1 (
  echo [ERROR] pip install fail ho gaya. Upar error dekho.
  pause
  exit /b 1
)
echo.
echo Demo data seed kar raha hoon...
python seed.py
if errorlevel 1 (
  echo [WARNING] seed mein masla hua - phir bhi aage barh raha hoon.
)
cd ..

echo.
echo ---- Frontend setup ----
cd frontend
if not exist "node_modules" (
  echo npm packages install ho rahe hain...
  call npm install
  if errorlevel 1 ( echo [ERROR] npm install fail. & pause & exit /b 1 )
) else (
  echo [OK] node_modules pehle se hai
)
cd ..

echo.
echo ================================================
echo  Setup mukammal! Ab START_WINDOWS.bat chalao.
echo ================================================
pause

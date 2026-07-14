@echo off
REM ============================================================
REM  SSD Recovery - one-click local run for Windows (no Docker)
REM  Uses a local SQLite file so you don't need Postgres either.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- pick python launcher ---
where py >nul 2>nul && (set PY=py) || (set PY=python)

echo.
echo [1/4] Creating virtual environment (.venv)...
%PY% -m venv .venv
if errorlevel 1 goto :nopython

call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies (first run only, ~1-2 min)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 goto :piperr

REM --- local SQLite DB + dev secret (no Postgres needed) ---
set DATABASE_URL=sqlite:///./ssd_local.db
set SECRET_KEY=local-dev-secret-change-me

echo [3/4] Seeding demo staff (admin / field officers / telecallers)...
python -m app.seed

echo [4/4] Starting server...
echo.
echo   =====================================================
echo     Open in your browser:   http://localhost:8000
echo     Login: admin@ssdrecovery.in  /  admin123
echo     (Press CTRL+C here to stop the server)
echo   =====================================================
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto :eof

:nopython
echo.
echo  ERROR: Python was not found.
echo  Install Python 3.11+ from https://www.python.org/downloads/
echo  During install, TICK "Add python.exe to PATH", then run this file again.
pause
goto :eof

:piperr
echo.
echo  ERROR: dependency install failed. Check your internet connection and re-run.
pause
goto :eof

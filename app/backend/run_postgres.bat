@echo off
REM ============================================================
REM  SSD Recovery - PRODUCTION run on PostgreSQL (Windows)
REM  Uses the DATABASE_URL in your .env (localhost Postgres).
REM  Prereq: PostgreSQL installed + database/user created, and
REM          data migrated once (see POSTGRES_SETUP.md).
REM ============================================================
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py) || (set PY=python)

if not exist ".venv\Scripts\activate.bat" (
  echo [setup] Creating virtual environment (.venv)...
  %PY% -m venv .venv
  if errorlevel 1 goto :nopython
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

REM --- DO NOT set DATABASE_URL here: the app reads it from .env (PostgreSQL). ---
REM --- Set a strong SECRET_KEY in .env for production. ---
set SEED_ON_START=1
set ENVIRONMENT=production

echo.
echo   =====================================================
echo     Starting on PostgreSQL (from .env DATABASE_URL).
echo     The startup log prints:  [SSD] Database: PostgreSQL -> ...
echo     Open:   http://localhost:8000
echo     (Press CTRL+C to stop)
echo   =====================================================
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto :eof

:nopython
echo  ERROR: Python was not found. Install Python 3.11+ and tick "Add python.exe to PATH".
pause
goto :eof

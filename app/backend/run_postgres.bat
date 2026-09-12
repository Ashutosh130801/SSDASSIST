@echo off
REM ============================================================
REM  SSD Recovery - PRODUCTION run on PostgreSQL (Windows)
REM  Uses the DATABASE_URL in your .env (localhost Postgres).
REM  This window ALWAYS stays open (pause at the end) so you can
REM  read any error instead of it flashing and closing.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   RecoverIQ / SSD - starting on PostgreSQL
echo ============================================================

REM --- 1) find Python (PREFER 3.12 / 3.11 — they have prebuilt wheels for all deps).
REM     Python 3.13/3.14 are too new: psycopg2, pydantic-core etc. have no wheels yet and
REM     would try to compile from source (needs Visual C++ / Rust) and fail. ---
set "PY="
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3.11 --version >nul 2>nul && set "PY=py -3.11"
if not defined PY py -3.10 --version >nul 2>nul && set "PY=py -3.10"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo  ERROR: Python was not found on this PC.
  echo  Install Python 3.12 ^(64-bit^) from https://www.python.org/downloads/release/python-3128/
  echo  and TICK "Add python.exe to PATH", then run this again.
  goto :end
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo   Python: !PYVER!
echo !PYVER! | findstr /R "3\.1[3-9] 3\.[2-9][0-9]" >nul
if not errorlevel 1 (
  echo.
  echo  ERROR: !PYVER! is too new — several dependencies have no prebuilt wheels for it,
  echo         so pip tries to COMPILE them and fails ^(needs Visual C++ / Rust^).
  echo.
  echo  FIX: install Python 3.12 ^(64-bit^):  https://www.python.org/downloads/release/python-3128/
  echo       During install TICK "Add python.exe to PATH".
  echo       Then delete the .venv folder here and run this file again — it will
  echo       automatically use 3.12 ^(no build tools needed^).
  goto :end
)

REM --- 2) virtual environment ---
if not exist ".venv\Scripts\activate.bat" (
  echo   [setup] Creating virtual environment ^(.venv^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo.
    echo  ERROR: could not create the virtual environment.
    goto :end
  )
)
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo.
  echo  ERROR: could not activate .venv. Delete the .venv folder and re-run.
  goto :end
)

REM --- 3) dependencies (non-fatal: keep going if offline) ---
echo   [deps] Installing / updating dependencies...
python -m pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt
if errorlevel 1 echo   [warn] Some packages could not be (re)installed ^(offline?^). Continuing with what's in .venv.

REM --- 4) config checks ---
if not exist ".env" (
  echo.
  echo  ERROR: .env not found in app\backend.
  echo  Create it with at least DATABASE_URL, SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD.
  echo  See SETUP_FROM_SCRATCH.md step 4.
  goto :end
)
findstr /I /C:"DATABASE_URL" .env | findstr /I "postgres" >nul
if errorlevel 1 (
  echo.
  echo  WARNING: .env DATABASE_URL does not look like a PostgreSQL URL.
  echo  It should be:  DATABASE_URL=postgresql+psycopg2://ssd:PASSWORD@localhost:5432/ssd_recovery
  echo.
)

REM --- production: create admin from .env on first start (no demo data) ---
set SEED_ON_START=1
set ENVIRONMENT=production

REM --- 5) quick Postgres reachability check (clear message if the DB is down) ---
echo   [db] Checking the database connection...
python -c "from app.config import get_settings; from sqlalchemy import create_engine, text; e=create_engine(get_settings().database_url); c=e.connect(); c.execute(text('select 1')); c.close(); print('   DB OK')"
if errorlevel 1 (
  echo.
  echo  ERROR: cannot connect to PostgreSQL using the DATABASE_URL in .env.
  echo  Fix one of these, then re-run:
  echo    - Is PostgreSQL running?  ^(services.msc -^> postgresql, or start the Postgres app^)
  echo    - Do the user/db/password in .env match what you created in psql?
  echo    - Is it listening on localhost:5432 ?
  echo  See SETUP_FROM_SCRATCH.md steps 1-2 and 4.
  goto :end
)

echo.
echo   =====================================================
echo     Starting on PostgreSQL ^(from .env DATABASE_URL^).
echo     The log should say:  [SSD] Database: PostgreSQL -^> ...
echo     Open:   http://localhost:8000
echo     Press CTRL+C here to stop the server.
echo   =====================================================
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo   The server has stopped.

:end
echo.
pause
endlocal

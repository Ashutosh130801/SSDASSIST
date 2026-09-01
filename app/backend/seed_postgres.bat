@echo off
REM ============================================================
REM  GO LIVE on PostgreSQL (run ONCE): create real admin, import
REM  the real employees, purge demo/test cases, map real cases.
REM  Targets the PostgreSQL in your .env (NOT sqlite).
REM
REM  Place these two files one folder above "app":
REM     SSDE Man power.xlsx
REM     SSDE_login_credentials.xlsx
REM  Prereq: PostgreSQL ready (see POSTGRES_SETUP.md). If you had
REM  data in SQLite, run migrate_sqlite_to_postgres.py FIRST.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo  Run run_postgres.bat once first so the virtual environment exists, then run this.
  pause
  goto :eof
)
call .venv\Scripts\activate.bat

REM --- DO NOT override DATABASE_URL: use .env PostgreSQL so we seed the SAME DB the server reads. ---

set MANPOWER=%~dp0..\..\SSDE Man power.xlsx
set CREDS=%~dp0..\..\SSDE_login_credentials.xlsx

if not exist "%MANPOWER%" (
  echo  ERROR: "SSDE Man power.xlsx" not found in the project root. Put it there and re-run.
  pause
  goto :eof
)

echo Seeding production data into PostgreSQL ^(hashes passwords, ~1 minute^)...
python productionize.py "%MANPOWER%" "%CREDS%"

echo.
echo  Done. Start the app with run_postgres.bat and log in as:
echo     admin@ssdenterprises.in  /  Admin@2006
echo.
pause

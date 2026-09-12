@echo off
REM ============================================================
REM  Seed ALL staff into PostgreSQL from the curated manpower sheet.
REM  Uses the DATABASE_URL in your .env (PostgreSQL) — NOT sqlite.
REM  Keeps every Emp Code as-is; gives dual-role people both hats.
REM
REM  Usage:
REM     seed_manpower.bat                         (looks for the sheet in the project root)
REM     seed_manpower.bat "C:\path\to\SSDE_manpower (7).xlsx"
REM
REM  Prereq: run_postgres.bat once first (creates .venv + tables).
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo  Run run_postgres.bat once first so the virtual environment exists, then run this.
  pause
  goto :eof
)
call .venv\Scripts\activate.bat

REM --- DO NOT override DATABASE_URL: use .env PostgreSQL so we seed the same DB the server reads ---

set SHEET=%~1
if "%SHEET%"=="" set SHEET=%~dp0..\..\SSDE_manpower.xlsx

if not exist "%SHEET%" (
  echo  ERROR: manpower sheet not found: "%SHEET%"
  echo  Pass the path explicitly, e.g.:  seed_manpower.bat "C:\Users\sahoo\Downloads\SSDE_manpower (7).xlsx"
  pause
  goto :eof
)

echo Seeding staff into PostgreSQL from "%SHEET%" ...
python seed_manpower.py "%SHEET%"
echo.
echo  Done. Start the app with run_postgres.bat and log in as:
echo     admin@ssdenterprises.in  /  Admin@2006
echo  Staff first-login password:  Ssd@2026  (they must change it on first login)
echo.
pause
endlocal

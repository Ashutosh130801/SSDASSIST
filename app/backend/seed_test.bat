@echo off
REM ============================================================
REM  Load the ICICI FR TEST dataset (5 branches, FOS/callers, 993 cases)
REM  into the SAME local SQLite DB the server uses (ssd_local.db).
REM  Run this ONCE, then start the app with run_local.bat.
REM  Logins: admin@ssd.local / Test@1234  (see TEST_LOGINS.md)
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo  Run run_local.bat once first so the virtual environment exists, then run this.
  pause
  goto :eof
)
call .venv\Scripts\activate.bat

REM --- MUST match run_local.bat so we seed the DB the server reads ---
set DATABASE_URL=sqlite:///./ssd_local.db
set SECRET_KEY=local-dev-secret-change-me

echo Seeding test data into ssd_local.db ...
python seed_fr_test.py

echo.
echo  Done. Now start the app with run_local.bat and log in as:
echo     admin@ssd.local  /  Test@1234
echo  (full staff list is in TEST_LOGINS.md)
echo.
pause

@echo off
REM ============================================================
REM  GO LIVE (run ONCE): create real admin, import the 189 real
REM  employees, PURGE the demo/test cases, map any real cases onto
REM  the new staff, and switch off the demo/test logins. No test data.
REM  Run run_local.bat afterwards.
REM
REM  Place these two files in the project root (one folder above "app"):
REM     SSDE Man power.xlsx
REM     SSDE_login_credentials.xlsx
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo  Run run_local.bat once first so the virtual environment exists, then run this.
  pause
  goto :eof
)
call .venv\Scripts\activate.bat

REM --- keep dependencies current (installs any newly-added packages, e.g. fpdf2) ---
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

REM --- MUST match run_local.bat so we touch the same DB the server reads ---
set DATABASE_URL=sqlite:///./ssd_local.db
set SECRET_KEY=local-dev-secret-change-me

set MANPOWER=%~dp0..\..\SSDE Man power.xlsx
set CREDS=%~dp0..\..\SSDE_login_credentials.xlsx

if not exist "%MANPOWER%" (
  echo  ERROR: "SSDE Man power.xlsx" not found in the project root. Put it there and re-run.
  pause
  goto :eof
)

echo Setting up production data ^(this hashes 189 passwords, ~1 minute^)...
python productionize.py "%MANPOWER%" "%CREDS%"

echo.
echo  Done. Start the app with run_local.bat and log in as:
echo     admin@ssdenterprises.in  /  Admin@2006
echo  Staff use the IDs + password Ssd@2026 from SSDE_login_credentials.xlsx
echo  (they'll be asked to set a new password on first login).
echo.
pause

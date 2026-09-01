@echo off
REM ============================================================
REM  SSD Recovery - PostgreSQL backup (safe while the app runs)
REM  Writes a compressed dump to .\backups\ and prunes old ones.
REM  Run it manually, or schedule it nightly (see POSTGRES_SETUP.md).
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- EDIT if your password/db differ (keep in sync with .env DATABASE_URL) ---
set PGURL=postgresql://ssd:ssd_password@localhost:5432/ssd_recovery
set OUTDIR=%~dp0backups
set KEEP_DAYS=14

REM If pg_dump isn't on PATH, set the full path to the Postgres bin here, e.g.:
REM set "PATH=C:\Program Files\PostgreSQL\16\bin;%PATH%"

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set FILE=%OUTDIR%\ssd_%TS%.dump

echo Backing up PostgreSQL to:
echo   %FILE%
pg_dump "%PGURL%" -Fc -f "%FILE%"
if errorlevel 1 (
  echo.
  echo  BACKUP FAILED. Check that:
  echo    - PostgreSQL is running
  echo    - pg_dump is on PATH ^(or set the bin path above^)
  echo    - the password in PGURL matches .env
  exit /b 1
)

echo Backup OK.
REM Delete dumps older than KEEP_DAYS.
powershell -NoProfile -Command "Get-ChildItem '%OUTDIR%\*.dump' ^| Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-%KEEP_DAYS%) } ^| Remove-Item -Force"
echo Pruned dumps older than %KEEP_DAYS% days.
echo Done.

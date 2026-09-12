@echo off
REM ============================================================
REM  SSD Recovery - PostgreSQL backup (safe while the app runs)
REM  Writes a compressed dump to .\backups\ and prunes old ones.
REM  The connection is read straight from .env's DATABASE_URL, so
REM  the password can never drift out of sync with the app.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set OUTDIR=%~dp0backups
set KEEP_DAYS=14

REM If pg_dump isn't on PATH, uncomment and point to your Postgres bin:
REM set "PATH=C:\Program Files\PostgreSQL\18\bin;%PATH%"

REM --- read DATABASE_URL from .env and make it pg_dump-friendly ---
set "DBURL="
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b /i "DATABASE_URL=" ".env"`) do set "DBURL=%%b"
)
if not defined DBURL (
  echo.
  echo  ERROR: DATABASE_URL not found in app\backend\.env
  echo  Add it, e.g.:  DATABASE_URL=postgresql+psycopg2://ssd:YOURPASS@localhost:5432/ssd_recovery
  goto :end
)
REM pg_dump doesn't understand the SQLAlchemy "+psycopg2" driver suffix - strip it.
set "PGURL=!DBURL:+psycopg2=!"
REM strip any surrounding quotes/spaces
set "PGURL=!PGURL:"=!"

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set FILE=%OUTDIR%\ssd_%TS%.dump

echo Backing up PostgreSQL to:
echo   %FILE%
pg_dump "!PGURL!" -Fc -f "%FILE%"
if errorlevel 1 (
  echo.
  echo  BACKUP FAILED. Check that:
  echo    - PostgreSQL is running
  echo    - pg_dump is on PATH ^(or set the bin path near the top of this file^)
  echo    - DATABASE_URL in .env is correct ^(same one the app uses^)
  goto :end
)

echo Backup OK.
REM Delete dumps older than KEEP_DAYS.
powershell -NoProfile -Command "Get-ChildItem '%OUTDIR%\*.dump' ^| Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-%KEEP_DAYS%) } ^| Remove-Item -Force"
echo Pruned dumps older than %KEEP_DAYS% days.
echo Done.

:end
echo.
pause
endlocal

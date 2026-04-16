@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 scripts\smart_start.py %*
) else (
    python scripts\smart_start.py %*
)

exit /b %errorlevel%

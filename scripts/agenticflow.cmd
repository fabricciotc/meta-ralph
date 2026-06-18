@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%.."

where python >nul 2>nul
if %errorlevel% == 0 (
    python "%REPO_ROOT%\dashboard\launcher.py" %*
    exit /b %errorlevel%
)

where python3 >nul 2>nul
if %errorlevel% == 0 (
    python3 "%REPO_ROOT%\dashboard\launcher.py" %*
    exit /b %errorlevel%
)

echo Error: python or python3 is not installed.
exit /b 1

@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "SCRIPT_DIR=%%~fI"

where bash >nul 2>nul
if errorlevel 1 (
  echo Error: Git Bash is required. Install Git for Windows or run install.ps1.
  exit /b 1
)

for /f "delims=" %%B in ('where bash ^| findstr /i "\\Git\\bin\\bash.exe"') do set "BASH=%%B"
if not defined BASH for /f "delims=" %%B in ('where bash') do set "BASH=%%B"

"%BASH%" "%SCRIPT_DIR%meta-ralph.sh" %*

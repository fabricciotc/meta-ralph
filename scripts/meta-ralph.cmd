@echo off
setlocal

set "GIT_BASH=C:\Program Files\Git\bin\bash.exe"
set "SCRIPT=%~dp0meta-ralph.sh"
set "SCRIPT=%SCRIPT:\=/%"

if not exist "%GIT_BASH%" (
  set "GIT_BASH=C:\Program Files (x86)\Git\bin\bash.exe"
)

if not exist "%GIT_BASH%" (
  echo Error: Git Bash is required to run meta-ralph on Windows.
  echo Install Git for Windows or set META_RALPH_GIT_BASH to your bash.exe path.
  exit /b 1
)

"%GIT_BASH%" "%SCRIPT%" %*
exit /b %ERRORLEVEL%

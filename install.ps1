#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptDir = Join-Path $SkillDir "scripts"
$Script = Join-Path $ScriptDir "meta-ralph.sh"
$DashboardDir = Join-Path $SkillDir "dashboard"
$VenvDir = Join-Path $DashboardDir ".venv"

function Find-Python {
    foreach ($candidate in @("python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    throw "Python 3.10+ is required but was not found on PATH."
}

function Get-VenvPython {
    param([string]$Venv)
    Join-Path $Venv "Scripts\python.exe"
}

function Get-VenvPip {
    param([string]$Venv)
    Join-Path $Venv "Scripts\pip.exe"
}

if (-not (Test-Path $Script)) {
    throw "Missing script: $Script"
}

$python = Find-Python
$version = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$version -lt [version]"3.10") {
    throw "Python 3.10+ is required. Detected: $version"
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating dashboard virtual environment..."
    & $python -m venv $VenvDir
    & (Get-VenvPip $VenvDir) install -q --upgrade pip
    & (Get-VenvPip $VenvDir) install -q -r (Join-Path $DashboardDir "requirements.txt")
}

$binDir = Join-Path $env:USERPROFILE ".local\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

$launcher = @"
@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=$($ScriptDir -replace '\\', '/')"
for /f "delims=" %%B in ('where bash ^| findstr /i "\\Git\\bin\\bash.exe"') do set "BASH=%%B"
if not defined BASH for /f "delims=" %%B in ('where bash') do set "BASH=%%B"
if not defined BASH (
  echo Error: Git Bash is required.
  exit /b 1
)
"%%BASH%%" "$($Script -replace '\\', '/')" %*
"@

Set-Content -Path (Join-Path $binDir "meta-ralph.cmd") -Value $launcher -Encoding ASCII
Write-Host "Created Windows launcher: $(Join-Path $binDir 'meta-ralph.cmd')"

$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$binDir;$currentPath", "User")
    Write-Host "Added $binDir to user PATH."
}

Write-Host ""
Write-Host "Meta-Ralph installed for Windows."
Write-Host "Restart your terminal, then run:"
Write-Host "  meta-ralph init"
Write-Host "  meta-ralph dashboard"

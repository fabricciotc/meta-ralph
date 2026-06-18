#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$AppDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $AppDir) {
    throw "Run this script as a file: .\install.ps1 (do not paste it into the console)."
}
$ScriptDir = Join-Path $AppDir "scripts"
$DashboardDir = Join-Path $AppDir "dashboard"
$VenvDir = Join-Path $DashboardDir ".venv"
$StateDir = Join-Path $AppDir ".agenticflow"

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

if (-not (Test-Path (Join-Path $DashboardDir "launcher.py"))) {
    throw "Missing dashboard launcher: $(Join-Path $DashboardDir 'launcher.py')"
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

New-Item -ItemType Directory -Force -Path (Join-Path $StateDir "state") | Out-Null

$configPath = Join-Path $StateDir "config.json"
if (-not (Test-Path $configPath)) {
    $config = @"
{
  "preferred_backends": ["kimi", "claude", "cursor", "copilot", "codex", "openai_api"],
  "model_overrides": {
    "openai_api": "gpt-4o-mini"
  },
  "timeout_defaults": {
    "pm_research": 600,
    "architect": 600,
    "planning": 600,
    "engineer": 1800,
    "qa": 600
  },
  "api_key_path": "~/.config/agenticflow/openai_api_key"
}
"@
    Set-Content -Path $configPath -Value $config -Encoding ASCII
    Write-Host "Created default config: $configPath"
}

$prdPath = Join-Path $StateDir "prd.json"
if (-not (Test-Path $prdPath)) {
    $prd = @"
{
  "projectName": "Example",
  "stories": [
    {
      "id": "US-001",
      "title": "Example story",
      "description": "Describe the user story here."
    }
  ]
}
"@
    Set-Content -Path $prdPath -Value $prd -Encoding ASCII
    Write-Host "Created example PRD: $prdPath"
}

$binDir = Join-Path $env:USERPROFILE ".local\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

$agenticflowLauncher = @"
@echo off
setlocal EnableExtensions
set "REPO_ROOT=$AppDir"

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
"@

Set-Content -Path (Join-Path $binDir "agenticflow.cmd") -Value $agenticflowLauncher -Encoding ASCII
Write-Host "Created Windows launcher: $(Join-Path $binDir 'agenticflow.cmd')"

$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$binDir;$currentPath", "User")
    Write-Host "Added $binDir to user PATH."
}

Write-Host ""
Write-Host "AgenticFlow installed for Windows."
Write-Host ""
Write-Host "To start the local engine and open the dashboard:"
Write-Host "  agenticflow start"
Write-Host ""
Write-Host "Then install the PWA from Chrome/Edge:"
Write-Host "  1. Open http://localhost:5050"
Write-Host "  2. Click the install icon in the address bar (or menu > Install AgenticFlow)"

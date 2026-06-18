#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptDir = Join-Path $SkillDir "scripts"
$LegacyScript = Join-Path $ScriptDir "meta-ralph.sh"
$AgenticflowScript = Join-Path $ScriptDir "agenticflow"
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

# Create application data directory and default config.
$dataDir = Join-Path $env:LOCALAPPDATA "AgenticFlow"
$stateDir = Join-Path $dataDir "state"
$logsDir = Join-Path $dataDir "logs"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$configFile = Join-Path $dataDir "config.json"
if (-not (Test-Path $configFile)) {
    @'
{
  "preferredBackend": null,
  "backendConfig": {},
  "projectsRoot": null,
  "maxWorkers": 10
}
'@ | Set-Content -Path $configFile -Encoding UTF8
    Write-Host "Created default config at $configFile"
}

$prdTemplate = Join-Path $SkillDir "assets\prd-template.json"
$prdFile = Join-Path $stateDir "prd.json"
if (-not (Test-Path $prdFile) -and (Test-Path $prdTemplate)) {
    Copy-Item -Path $prdTemplate -Destination $prdFile -Force
    Write-Host "Created PRD template at $prdFile"
}

if (Test-Path $LegacyScript) {
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
"%%BASH%%" "$($LegacyScript -replace '\\', '/')" %*
"@
    Set-Content -Path (Join-Path $binDir "meta-ralph.cmd") -Value $launcher -Encoding ASCII
    Write-Host "Created Windows launcher: $(Join-Path $binDir 'meta-ralph.cmd')"
}

$agenticflowCmd = Join-Path $ScriptDir "agenticflow.cmd"
if (Test-Path $agenticflowCmd) {
    Copy-Item -Path $agenticflowCmd -Destination (Join-Path $binDir "agenticflow.cmd") -Force
    Write-Host "Created Windows launcher: $(Join-Path $binDir 'agenticflow.cmd')"
}

$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$binDir;$currentPath", "User")
    Write-Host "Added $binDir to user PATH."
}

Write-Host ""
Write-Host "Detected AI backends:"
$BACKENDS_FOUND = 0
function Detect-Backend {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "  ok: $Name"
        $global:BACKENDS_FOUND++
    } else {
        Write-Host "  missing: $Name"
    }
}

Detect-Backend "kimi"
Detect-Backend "claude"
if ((Get-Command "cursor-agent" -ErrorAction SilentlyContinue) -or (Get-Command "agent" -ErrorAction SilentlyContinue)) {
    Write-Host "  ok: cursor-agent"
    $global:BACKENDS_FOUND++
} else {
    Write-Host "  missing: cursor-agent"
}
Detect-Backend "codex"
if ((Get-Command "copilot" -ErrorAction SilentlyContinue) -or (Get-Command "gh" -ErrorAction SilentlyContinue)) {
    Write-Host "  ok: copilot"
    $global:BACKENDS_FOUND++
} else {
    Write-Host "  missing: copilot"
}
if ($env:OPENAI_API_KEY) {
    Write-Host "  ok: openai_api (OPENAI_API_KEY is set)"
    $global:BACKENDS_FOUND++
} else {
    Write-Host "  missing: openai_api (OPENAI_API_KEY is not set)"
}

if ($BACKENDS_FOUND -eq 0) {
    Write-Host ""
    Write-Host "No AI backend was detected yet. The dashboard will ask you to link one when it starts."
    Write-Host "Supported options:"
    Write-Host "  - kimi (Kimi Code CLI)"
    Write-Host "  - claude (Claude Code CLI)"
    Write-Host "  - cursor-agent / agent (Cursor agent CLI)"
    Write-Host "  - codex (Codex CLI)"
    Write-Host "  - copilot / gh (GitHub Copilot CLI)"
    Write-Host "  - OPENAI_API_KEY environment variable"
}

Write-Host ""
Write-Host "AgenticFlow installed for Windows."
Write-Host ""
Write-Host "Data directory: $dataDir"
Write-Host ""
Write-Host "To start the local engine and open the dashboard:"
Write-Host "  agenticflow start"
Write-Host ""
Write-Host "Legacy CLI still works:"
Write-Host "  meta-ralph init"
Write-Host "  meta-ralph dashboard"

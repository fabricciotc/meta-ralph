# Build the AgenticFlow Python sidecar for the current Windows host.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$TargetTriple = (rustc --print host-tuple).Trim()
$SidecarName = "dashboard-server-$TargetTriple.exe"

Set-Location dashboard

if (-not (Test-Path .venv)) {
    Write-Host "Creating dashboard virtual environment..."
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1

python -m pip install -q --upgrade pip pyinstaller
python -m pip install -q -r requirements.txt

Write-Host "Building sidecar with PyInstaller..."
pyinstaller --onefile --name dashboard-server `
    --add-data "static;static" `
    --add-data "core/role_skills_registry.yaml;core" `
    server.py

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path src-tauri\binaries | Out-Null

Copy-Item dashboard\dist\dashboard-server.exe "src-tauri\binaries\$SidecarName" -Force

Write-Host "Sidecar ready: src-tauri\binaries\$SidecarName"

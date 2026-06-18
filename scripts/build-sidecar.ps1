# Build the AgenticFlow Python sidecar for the current Windows host.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$TargetTriple = (rustc --print host-tuple).Trim()
$SidecarName = "dashboard-server-$TargetTriple.exe"

Set-Location dashboard

# Prefer uv + a standalone CPython to avoid Anaconda/PyInstaller runtime issues.
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Using uv to build the sidecar..."
    uv python install 3.12
    uv venv --python 3.12 .venv-uv
    .\.venv-uv\Scripts\Activate.ps1
    uv pip install -r requirements.txt pyinstaller
} else {
    Write-Host "uv not found; falling back to system python venv..."
    if (-not (Test-Path .venv)) {
        Write-Host "Creating dashboard virtual environment..."
        python -m venv .venv
    }
    .\.venv\Scripts\Activate.ps1
    python -m pip install -q --upgrade pip pyinstaller
    python -m pip install -q -r requirements.txt
}

Write-Host "Building sidecar with PyInstaller..."
pyinstaller -y --onefile --name dashboard-server `
    --add-data "static;static" `
    --add-data "core/role_skills_registry.yaml;core" `
    --hidden-import engineio.async_drivers.threading `
    server.py

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path src-tauri\binaries | Out-Null

Remove-Item "src-tauri\binaries\$SidecarName" -ErrorAction SilentlyContinue
Copy-Item dashboard\dist\dashboard-server.exe "src-tauri\binaries\$SidecarName" -Force

Write-Host "Sidecar ready: src-tauri\binaries\$SidecarName"

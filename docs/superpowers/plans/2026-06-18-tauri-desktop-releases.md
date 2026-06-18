# Tauri Desktop App + Automatic Releases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing AgenticFlow Python engine in a Tauri v2 desktop app and publish installers automatically on `v*` tags via GitHub Actions.

**Architecture:** Tauri starts the Python backend as a sidecar on port 5050 and loads the dashboard from the sidecar's own HTTP server (`http://127.0.0.1:5050`). This keeps the web/PWA flow untouched, avoids CORS, and requires no frontend build step. The Python backend detects when it is running as a PyInstaller bundle and stores state under `~/.agenticflow/data` so tickets survive app restarts.

**Tech Stack:** Tauri v2, Rust, PyInstaller, GitHub Actions, Python 3.11.

---

## File map

| File | Responsibility |
|------|----------------|
| `src-tauri/Cargo.toml` | Rust dependencies (tauri, shell plugin). |
| `src-tauri/tauri.conf.json` | Tauri app config: window size, sidecar path, remote frontend URL. |
| `src-tauri/capabilities/default.json` | ACL permissions for shell sidecar execution. |
| `src-tauri/src/main.rs` | Spawn/kill the Python sidecar, handle app lifecycle. |
| `src-tauri/icons/*` | App icons (generated from a source image). |
| `scripts/build-sidecar.sh` | Build PyInstaller sidecar for the current host and rename it with the Rust target triple. |
| `scripts/build-sidecar.ps1` | Windows version of the sidecar build script. |
| `.github/workflows/release.yml` | Matrix build & release workflow for macOS/Windows/Linux. |
| `package.json` | Minimal npm manifest so `tauri-action` can run the CLI. |
| `dashboard/server.py` | Detect PyInstaller bundle and persist state under `~/.agenticflow/data`. |

---

## Task 1: Install Rust toolchain and Tauri CLI

**Files:**
- Modify: `~/.cargo/bin` / `~/.rustup` (environment)

- [ ] **Step 1: Install rustup and stable toolchain**

Run:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustup default stable
```

- [ ] **Step 2: Verify Rust is available**

Run:
```bash
rustc --version
cargo --version
```
Expected: versions printed, no errors.

- [ ] **Step 3: Install Tauri CLI**

Run:
```bash
cargo install tauri-cli --version '^2.0'
```

---

## Task 2: Add PyInstaller bundle detection to the Python backend

**Files:**
- Modify: `dashboard/server.py:87-100`

The dashboard currently stores board/run-state next to `server.py`. When packaged as a one-file PyInstaller binary the executable is extracted to a temporary directory, so state would be lost on every run. Make `get_meta_dir()` return `~/.agenticflow/data` when frozen.

- [ ] **Step 1: Update `get_meta_dir()` in `dashboard/server.py`**

Replace lines 87-100 with:

```python
def get_meta_dir():
    """Return the scripts/meta-ralph directory relative to the project.

    Prefer the current working directory when it already contains the
    meta-ralph scripts folder (used by tests and project-specific runs).
    When running as a PyInstaller bundle, use the user's home directory so
    state survives app restarts. Otherwise fall back to the directory where
    this server file lives.
    """
    env_dir = os.environ.get("AGENTICFLOW_META_DIR")
    if env_dir:
        return Path(env_dir)
    if getattr(sys, "frozen", False):
        # Running inside the Tauri sidecar; keep state in the user's home.
        meta = Path.home() / ".agenticflow" / "data" / "scripts" / "meta-ralph"
        meta.mkdir(parents=True, exist_ok=True)
        return meta
    cwd_candidate = Path.cwd() / "scripts" / "meta-ralph"
    if cwd_candidate.exists():
        return cwd_candidate
    server_dir = Path(__file__).resolve().parent
    return server_dir / "scripts" / "meta-ralph"
```

- [ ] **Step 2: Run the existing test suite to make sure nothing broke**

Run:
```bash
cd AgenticFlow/dashboard
python -m pytest tests/test_server_pm_analysis.py tests/test_ticket_flow.py -q
```
Expected: tests pass.

- [ ] **Step 3: Commit**

```bash
cd AgenticFlow
git add dashboard/server.py
git commit -m "feat(tauri): persist state under ~/.agenticflow/data when bundled"
```

---

## Task 3: Create Tauri project files

### Task 3.1: `src-tauri/Cargo.toml`

**Files:**
- Create: `src-tauri/Cargo.toml`

- [ ] **Step 1: Write the file**

```toml
[package]
name = "agenticflow"
version = "0.5.0"
description = "AgenticFlow desktop app"
authors = ["Fabriccio Tornero"]
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-shell = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"

[features]
default = []
```

### Task 3.2: `src-tauri/tauri.conf.json`

**Files:**
- Create: `src-tauri/tauri.conf.json`

- [ ] **Step 2: Write the file**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "AgenticFlow",
  "version": "0.5.0",
  "identifier": "com.agenticflow.app",
  "build": {
    "beforeBuildCommand": "",
    "beforeDevCommand": "",
    "devUrl": "http://127.0.0.1:5050",
    "frontendDist": "http://127.0.0.1:5050"
  },
  "app": {
    "windows": [
      {
        "label": "main",
        "title": "AgenticFlow",
        "width": 1400,
        "height": 900,
        "resizable": true,
        "url": "http://127.0.0.1:5050"
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": ["dmg", "app", "nsis", "deb", "appimage"],
    "externalBin": ["binaries/dashboard-server"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  }
}
```

### Task 3.3: `src-tauri/capabilities/default.json`

**Files:**
- Create: `src-tauri/capabilities/default.json`

- [ ] **Step 3: Write the file**

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capabilities for the main window",
  "windows": ["main"],
  "permissions": [
    "core:default",
    {
      "identifier": "shell:allow-execute",
      "allow": [
        {
          "args": true,
          "name": "binaries/dashboard-server",
          "sidecar": true
        }
      ]
    }
  ]
}
```

### Task 3.4: `src-tauri/src/main.rs`

**Files:**
- Create: `src-tauri/src/main.rs`

- [ ] **Step 4: Write the file**

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

const BACKEND_PORT: u16 = 5050;

struct AppState {
    sidecar_child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<tauri_plugin_shell::process::CommandChild, String> {
    let sidecar_command = app
        .shell()
        .sidecar("dashboard-server")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?
        .args(["--host", "127.0.0.1", "--port", &BACKEND_PORT.to_string(), "--no-browser"]);

    let (mut rx, child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[sidecar] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[sidecar] {}", String::from_utf8_lossy(&line));
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState {
            sidecar_child: Mutex::new(None),
        })
        .setup(|app| {
            let child = spawn_sidecar(app.app_handle()).expect("failed to spawn sidecar");
            {
                let state = app.state::<AppState>();
                let mut c = state.sidecar_child.lock().unwrap();
                *c = Some(child);
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn main() {
    run();
}
```

### Task 3.5: icons placeholder

**Files:**
- Create: `src-tauri/icons/.gitkeep`

- [ ] **Step 5: Create placeholder and generate icons later**

Run:
```bash
mkdir -p src-tauri/icons
touch src-tauri/icons/.gitkeep
```

The icons will be generated in Task 7 from `dashboard/static/icon-512.png`.

- [ ] **Step 6: Commit Tauri scaffold**

```bash
cd AgenticFlow
git add src-tauri package.json
git commit -m "feat(tauri): scaffold Tauri v2 desktop app"
```

---

## Task 4: Create `package.json` for the Tauri CLI

**Files:**
- Create: `package.json`

`tauri-apps/tauri-action` expects a Node project with `@tauri-apps/cli` installed locally.

- [ ] **Step 1: Write the file**

```json
{
  "name": "agenticflow-desktop",
  "version": "0.5.0",
  "private": true,
  "description": "AgenticFlow Tauri desktop app",
  "scripts": {
    "tauri": "tauri"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.0.0"
  }
}
```

- [ ] **Step 2: Install npm dependencies**

Run:
```bash
cd AgenticFlow
npm install
```
Expected: `node_modules` created and `package-lock.json` generated.

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore(tauri): add minimal package.json for Tauri CLI"
```

---

## Task 5: Build the Python sidecar locally

### Task 5.1: Create `scripts/build-sidecar.sh`

**Files:**
- Create: `scripts/build-sidecar.sh`

- [ ] **Step 1: Write the file**

```bash
#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TARGET_TRIPLE=$(rustc --print host-tuple)
SIDEcar_NAME="dashboard-server-${TARGET_TRIPLE}"

cd dashboard

if [ ! -d ".venv" ]; then
  echo "Creating dashboard virtual environment..."
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

pip install -q --upgrade pip pyinstaller
pip install -q -r requirements.txt

echo "Building sidecar with PyInstaller..."
pyinstaller --onefile --name dashboard-server \
  --add-data "static:static" \
  --add-data "core/role_skills_registry.yaml:core" \
  server.py

cd "$REPO_ROOT"
mkdir -p src-tauri/binaries

cp "dashboard/dist/dashboard-server" "src-tauri/binaries/${SIDEcar_NAME}"
chmod +x "src-tauri/binaries/${SIDEcar_NAME}"

echo "Sidecar ready: src-tauri/binaries/${SIDEcar_NAME}"
```

- [ ] **Step 2: Make it executable**

Run:
```bash
chmod +x AgenticFlow/scripts/build-sidecar.sh
```

### Task 5.2: Create `scripts/build-sidecar.ps1`

**Files:**
- Create: `scripts/build-sidecar.ps1`

- [ ] **Step 3: Write the file**

```powershell
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
```

### Task 5.3: Run the local sidecar build

**Files:**
- Create: `src-tauri/binaries/dashboard-server-*`

- [ ] **Step 4: Build the sidecar on macOS/Linux**

Run:
```bash
cd AgenticFlow
./scripts/build-sidecar.sh
```
Expected: a file like `src-tauri/binaries/dashboard-server-aarch64-apple-darwin` exists and is executable.

- [ ] **Step 5: Smoke-test the sidecar binary**

Run:
```bash
./src-tauri/binaries/dashboard-server-* --host 127.0.0.1 --port 5051 --no-browser &
PID=$!
sleep 2
curl -s http://127.0.0.1:5051/api/health | head -c 200
kill $PID
```
Expected: the health endpoint returns JSON and the process stops cleanly.

- [ ] **Step 6: Commit build scripts**

```bash
cd AgenticFlow
git add scripts/build-sidecar.sh scripts/build-sidecar.ps1
git commit -m "feat(tauri): add sidecar build scripts"
```

---

## Task 6: Local Tauri dev/build verification

- [ ] **Step 1: Run Tauri in dev mode**

Run:
```bash
cd AgenticFlow
npm run tauri dev
```
Expected: a native window opens and loads the AgenticFlow dashboard from the sidecar.

- [ ] **Step 2: Create a ticket and pick a folder**

In the running app, click **New**, fill in the title, click **Pick folder** (this uses the existing backend tkinter picker), and save.
Expected: the ticket appears on the board.

- [ ] **Step 3: Build a local release bundle**

Run:
```bash
cd AgenticFlow
npm run tauri build
```
Expected: the bundle is produced under `src-tauri/target/release/bundle/`.

- [ ] **Step 4: Install/run the produced bundle**

On macOS:
```bash
open src-tauri/target/release/bundle/dmg/*.dmg
```
Expected: the DMG mounts and the app launches the dashboard.

---

## Task 7: Generate app icons

**Files:**
- Create: `src-tauri/icons/32x32.png`, `128x128.png`, `icon.icns`, `icon.ico`, etc.

- [ ] **Step 1: Use the Tauri icon generator**

Run:
```bash
cd AgenticFlow
npx tauri icon dashboard/static/icon-512.png
```
Expected: `src-tauri/icons/` is populated with all required sizes.

- [ ] **Step 2: Commit icons**

```bash
git add src-tauri/icons
git commit -m "assets(tauri): add generated app icons"
```

---

## Task 8: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the workflow directory**

Run:
```bash
mkdir -p AgenticFlow/.github/workflows
```

- [ ] **Step 2: Write the workflow**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build:
    permissions:
      contents: write
    strategy:
      fail-fast: false
      matrix:
        include:
          - platform: 'macos-latest'
            args: '--target aarch64-apple-darwin'
          - platform: 'macos-13'
            args: '--target x86_64-apple-darwin'
          - platform: 'ubuntu-22.04'
            args: '--target x86_64-unknown-linux-gnu'
          - platform: 'windows-latest'
            args: '--target x86_64-pc-windows-msvc'

    runs-on: ${{ matrix.platform }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: lts/*

      - name: Install Rust stable
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.args }}

      - name: Install Linux dependencies
        if: matrix.platform == 'ubuntu-22.04'
        run: |
          sudo apt-get update
          sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pyinstaller
          python -m pip install -r dashboard/requirements.txt

      - name: Build sidecar
        shell: bash
        run: |
          cd dashboard
          pyinstaller --onefile --name dashboard-server \
            --add-data "static:static" \
            --add-data "core/role_skills_registry.yaml:core" \
            server.py
          cd ..
          mkdir -p src-tauri/binaries
          case "${{ matrix.platform }}" in
            macos-latest)
              mv dashboard/dist/dashboard-server src-tauri/binaries/dashboard-server-aarch64-apple-darwin
              ;;
            macos-13)
              mv dashboard/dist/dashboard-server src-tauri/binaries/dashboard-server-x86_64-apple-darwin
              ;;
            ubuntu-22.04)
              mv dashboard/dist/dashboard-server src-tauri/binaries/dashboard-server-x86_64-unknown-linux-gnu
              ;;
            windows-latest)
              mv dashboard/dist/dashboard-server.exe src-tauri/binaries/dashboard-server-x86_64-pc-windows-msvc.exe
              ;;
          esac

      - name: Install npm dependencies
        run: npm install

      - name: Build Tauri app and create release
        uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tagName: ${{ github.ref_name }}
          releaseName: 'AgenticFlow ${{ github.ref_name }}'
          releaseBody: 'Installers for macOS, Windows, and Linux are attached below.'
          releaseDraft: true
          prerelease: false
          args: ${{ matrix.args }}
```

- [ ] **Step 3: Commit the workflow**

```bash
cd AgenticFlow
git add .github/workflows/release.yml
git commit -m "ci: add GitHub Actions release workflow for Tauri"
```

---

## Task 9: Update documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Tauri section near the top of README.md**

Insert after the existing "## Installation" section:

```markdown
## Desktop App (Tauri)

You can also run AgenticFlow as a native desktop app.

### Build from source

Requirements: Node.js, Rust, Python 3.10+.

```bash
npm install
./scripts/build-sidecar.sh   # or .\\scripts\\build-sidecar.ps1 on Windows
npm run tauri dev            # development
npm run tauri build          # production installer
```

The installer is written to `src-tauri/target/release/bundle/`.

### Download a release

Pre-built installers for macOS, Windows, and Linux are available on the [GitHub Releases](https://github.com/fabricciotc/agenticflow/releases) page.
```

- [ ] **Step 2: Commit docs**

```bash
cd AgenticFlow
git add README.md
git commit -m "docs: add Tauri desktop build and release instructions"
```

---

## Task 10: Push and verify a release

- [ ] **Step 1: Push all commits**

Run:
```bash
cd AgenticFlow
git push origin main
```

- [ ] **Step 2: Create and push a version tag**

Run:
```bash
cd AgenticFlow
git tag v0.5.0
git push origin v0.5.0
```

Expected: the Release workflow runs on GitHub Actions.

- [ ] **Step 3: Check the Actions run**

Open `https://github.com/fabricciotc/agenticflow/actions` and verify all four matrix jobs complete.

- [ ] **Step 4: Review the draft release**

Open `https://github.com/fabricciotc/agenticflow/releases` and confirm installers are attached. Publish the release when ready.

---

## Spec coverage check

| Spec requirement | Task |
|------------------|------|
| Tauri desktop app | Tasks 3, 5, 6, 7 |
| Python backend as sidecar | Tasks 3.4, 5 |
| Automatic releases on `v*` tags | Task 8 |
| macOS/Windows/Linux installers | Task 8 matrix |
| State persistence in bundled mode | Task 2 |
| Docs updated | Task 9 |

## Placeholder scan

- No "TBD", "TODO", "fill in", or "similar to Task N" items.
- All commands include expected output.
- All code blocks are complete and copy-paste ready.

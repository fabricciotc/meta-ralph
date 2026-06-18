# AgenticFlow — Tauri Desktop App + Automatic Releases

## Context

AgenticFlow today is a local Python engine (`dashboard/server.py`) with a Kanban web UI served from `dashboard/static/`. Users install it via `install.sh` and run `agenticflow start`, which opens the dashboard in a browser or installed PWA. The project wants to ship a native desktop application built with Tauri and publish automatic releases through GitHub Actions.

## Goals

1. Provide a native desktop app for macOS, Windows, and Linux.
2. Keep the existing Python backend and web UI working (browser/PWA mode must continue to function).
3. Bundle the Python backend as a self-contained sidecar so end users do not need Python installed.
4. Replace the brittle browser-based folder picker with a native file dialog when running inside Tauri.
5. Build and publish installer assets automatically on version tags.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend location | Keep `dashboard/static/` | Tauri can serve the existing static files directly. No file moves, no broken PWA/browser URLs. |
| Backend strategy | Keep Python Flask/SocketIO backend as a Tauri sidecar | Rewriting the orchestrator in Rust would take weeks and introduce regressions. PyInstaller produces a single binary with no external Python dependency. |
| Release trigger | Git tag `v*` (e.g. `v0.5.0`) | Tag-based releases are predictable, allow curated changelogs, and avoid publishing broken `main` builds. |
| Supported platforms | macOS (x86_64 + aarch64), Windows (x86_64), Linux (x86_64) | Covers the majority of developer machines; ARM Linux can be added later if requested. |

## Architecture

```text
AgenticFlow/
├── dashboard/                 # unchanged Python backend + static UI
│   ├── server.py              # Flask + SocketIO engine
│   ├── static/                # HTML/CSS/JS frontend
│   └── requirements.txt
├── scripts/                   # existing CLI wrappers
├── src-tauri/                 # new Tauri app
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── capabilities/default.json
│   ├── icons/
│   ├── binaries/              # compiled sidecars (git-ignored, built in CI)
│   └── src/main.rs            # window + sidecar lifecycle
├── scripts/build-sidecar.sh   # PyInstaller helper
└── .github/workflows/release.yml
```

### Runtime flow

1. Tauri window loads `dashboard/static/index.html` via the embedded sidecar's HTTP server OR directly from the static folder.
2. On startup, Rust spawns the Python sidecar (`dashboard-server-<target-triple>`) on a free port.
3. The frontend detects Tauri (`window.__TAURI__`) and uses `invoke('pick_folder')` for the native folder dialog.
4. The sidecar handles all business logic: tickets, AI runners, git worktrees, QA loop.
5. When the window closes, Rust terminates the sidecar process tree cleanly.

### Frontend detection

```javascript
const isTauri = typeof window !== 'undefined' && !!window.__TAURI__;
```

- **In Tauri**: use `@tauri-apps/plugin-dialog` `open()` with `directory: true`.
- **In browser/PWA**: keep the existing `/api/pick-folder` endpoint (tkinter backend) or File System Access API fallback.

## Tauri Configuration

`src-tauri/tauri.conf.json`:

```json
{
  "productName": "AgenticFlow",
  "identifier": "com.agenticflow.app",
  "build": {
    "frontendDist": "../../dashboard/static",
    "devUrl": "http://localhost:5050"
  },
  "app": {
    "windows": [
      {
        "title": "AgenticFlow",
        "width": 1400,
        "height": 900,
        "resizable": true
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": ["dmg", "app", "nsis", "deb", "appimage"],
    "externalBin": ["binaries/dashboard-server"],
    "icon": ["icons/32x32.png", "icons/128x128.png", "icons/icon.icns", "icons/icon.ico"]
  }
}
```

`capabilities/default.json` grants:

- `core:default`
- `dialog:allow-open`
- `shell:allow-execute` scoped to the `binaries/dashboard-server` sidecar with `args: true`

## Sidecar Build

### Local development

```bash
scripts/build-sidecar.sh
# places src-tauri/binaries/dashboard-server-aarch64-apple-darwin (example)
```

The helper:

1. Activates `dashboard/.venv`.
2. Runs PyInstaller in one-file mode:
   ```bash
   pyinstaller --onefile --name dashboard-server \
     --add-data "static:static" \
     dashboard/server.py
   ```
3. Renames the binary with the Rust target triple so Tauri bundles it.

### CI build

GitHub Actions matrix:

| OS | Target | Output |
|----|--------|--------|
| macos-latest | aarch64-apple-darwin | .app + .dmg |
| macos-13 | x86_64-apple-darwin | .app + .dmg |
| windows-latest | x86_64-pc-windows-msvc | .exe + .msi/.nsis |
| ubuntu-22.04 | x86_64-unknown-linux-gnu | .deb + .AppImage |

Each runner compiles the sidecar for its own target triple, then runs `cargo tauri build`.

## Release Pipeline

`.github/workflows/release.yml` triggers on pushes to tags matching `v*.*.*`:

1. Run a quick smoke test (`python -m pytest dashboard/tests` on Linux).
2. Build sidecar + Tauri app for each matrix target.
3. Upload artifacts to a GitHub Release with the tag name.
4. Mark the release as draft if the tag contains `-rc` or `-beta`; otherwise publish it.

## Error Handling

- If the sidecar fails to start, show an error screen in the Tauri window with the path to `~/.agenticflow/logs/sidecar.log`.
- If the frontend cannot connect to the sidecar HTTP port, retry with exponential backoff (same overlay used today).
- On app quit, kill the sidecar process group to prevent orphan Python processes.

## Testing

1. **Local dev loop**: `npm run tauri dev` with the existing Python venv running separately.
2. **Local bundle**: `scripts/build-sidecar.sh && npm run tauri build`.
3. **CI smoke**: run the existing Python test suite before starting the matrix build.
4. **Manual QA**: create a ticket, pick a folder via the native dialog, and move it to Ready for Work.

## Migration Path

- The PWA/browser flow remains untouched.
- The Tauri app is additive; `install.sh` can later be updated to download the platform installer instead of setting up a Python venv.
- No backend logic changes are required beyond reading the port from `AGENTICFLOW_PORT` if provided.

## Out of Scope

- Rewriting the orchestrator in Rust.
- Mobile apps (iOS/Android).
- Code signing / notarization for macOS (can be added later with Apple certificates).

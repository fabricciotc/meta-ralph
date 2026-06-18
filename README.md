# AgenticFlow

AgenticFlow is a standalone MetaGPT-style multi-agent orchestration app for AI coding assistants. It coordinates PM Research, Architecture, Planning, parallel Engineers, and QA with a local dashboard for ticket management and live progress.

## What It Does

- Takes a PRD or ticket and executes it through a five-phase loop: PM Analysis -> Architecture -> Planning -> Parallel Execution -> QA Review.
- Supports multiple PM Research agents and Engineer workers, capped by `--max-workers`.
- Gives each Engineer its own role context, feature focus, git worktree, and branch.
- Runs QA before integrating a batch back into trunk.
- Provides a Kanban dashboard at `http://localhost:5050` with live updates.
- Saves per-ticket run snapshots so a ticket can be paused, resumed, or restarted after the dashboard server restarts.

## Requirements

- Python 3.10+
- Git
- At least one AI runner:
  - `kimi`
  - `claude`
  - `cursor-agent` (or `agent` on Windows)
  - `copilot`
  - `codex`
  - `OPENAI_API_KEY` for OpenAI-compatible API mode
- Chrome or Edge (required for the File System Access API used by the PWA)

## Installation

### Option 1: Use The Installer

```bash
git clone https://github.com/fabricciotc/agenticflow.git
cd agenticflow
./install.sh
```

On Windows, use PowerShell:

```powershell
git clone https://github.com/fabricciotc/agenticflow.git
cd agenticflow
.\install.ps1
```

The installer:

1. Creates a Python virtual environment for the backend in `dashboard/.venv`.
2. Installs `dashboard/requirements.txt`.
3. Creates the `agenticflow` command in your PATH.
4. Reports which AI backends are available.

Restart your terminal or run `source ~/.zshrc` / `source ~/.bashrc` so the commands are available.

## Usage

### 1. Start the local engine

```bash
agenticflow start
```

This starts the Python backend. If you already installed the PWA, it opens the standalone app; otherwise it opens the dashboard in your default browser.

### 2. Install the PWA (first time only)

Open `http://localhost:5050` in Chrome/Edge and click the install icon in the address bar (or menu > **Install AgenticFlow**). Once installed, `agenticflow start` will detect the installed app and launch it directly.

### 3. Link an AI assistant

The first time the dashboard connects to the local engine it detects which AI CLIs are installed and asks you to pick one. The choice is saved in `.agenticflow/config.json`.

Supported options:

- `kimi` — Kimi Code CLI
- `claude` — Claude Code CLI
- `cursor-agent` / `agent` — Cursor agent CLI
- `copilot` — GitHub Copilot CLI
- `codex` — Codex CLI
- `OPENAI_API_KEY` — OpenAI-compatible API backend

### 4. Create a ticket and pick a folder

Create a ticket and use **Pick folder** to select the project directory with the native file picker. Because browsers cannot expose absolute paths, you still need to type or confirm the absolute path so the local engine can run `git`, builds, and AI CLIs on that folder.

### 5. Run the factory

Move the ticket to **Ready for Work** and the five-phase loop starts.

## Backend Selection

By default, the backend tries available backends in this order:

```bash
AGENTICFLOW_BACKENDS="kimi claude cursor copilot codex openai_api"
```

Force a backend:

```bash
AGENTICFLOW_BACKEND=claude agenticflow start
AGENTICFLOW_BACKEND=codex agenticflow start
AGENTICFLOW_BACKEND=cursor agenticflow start
AGENTICFLOW_BACKEND=copilot agenticflow start
AGENTICFLOW_BACKEND=kimi agenticflow start
```

## Project Layout

```text
agenticflow/
├── README.md                   # This file
├── install.sh                  # Program installer
├── assets/
│   └── prd-template.json       # Input PRD template
├── references/
│   ├── metagpt-roles.md        # Role SOPs
│   ├── orchestrator-prompt.md
│   ├── worker-prompt-template.md
│   └── qa-prompt-template.md
├── scripts/
│   ├── agenticflow             # Local engine launcher
│   ├── create-worktree.sh
│   ├── dispatch-workers.sh
│   └── ...
└── dashboard/
    ├── server.py               # Flask + SocketIO backend
    ├── static/                 # Kanban UI
    └── requirements.txt
```

## License

MIT

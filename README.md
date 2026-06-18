# AgenticFlow

AgenticFlow is a MetaGPT-style multi-agent orchestration skill for AI coding assistants. It coordinates PM Research, Architecture, Planning, parallel Engineers, and QA with a local dashboard for ticket management and live progress.

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
  - `codex`
  - `OPENAI_API_KEY` for OpenAI-compatible API mode
- Chrome or Edge (required for the File System Access API used by the PWA)

## Installation

### Option 1: Use The Installer

```bash
git clone https://github.com/fabricciotc/meta-ralph.git
cd meta-ralph
./install.sh
```

On Windows, use PowerShell:

```powershell
git clone https://github.com/fabricciotc/meta-ralph.git
cd meta-ralph
.\install.ps1
```

The installer:

1. Creates a Python virtual environment for the backend in `dashboard/.venv`.
2. Installs `dashboard/requirements.txt`.
3. Creates `agenticflow` and `meta-ralph` commands in your PATH.
4. Reports which AI backends are available.

Restart your terminal or run `source ~/.zshrc` / `source ~/.bashrc` so the commands are available.

### Option 2: Clone As An Assistant Skill

You can still install AgenticFlow as a skill for Kimi, Claude, Cursor, or Codex:

```bash
# Kimi
git clone https://github.com/fabricciotc/meta-ralph.git ~/.kimi-code/skills/meta-ralph
```

## Usage

### 1. Start the local engine

```bash
agenticflow start
```

This starts the Python backend. If you already installed the PWA, it opens the standalone app; otherwise it opens the dashboard in your default browser.

### 2. Install the PWA (first time only)

Open `http://localhost:5050` in Chrome/Edge and click the install icon in the address bar (or menu > **Install AgenticFlow**). Once installed, `agenticflow start` will detect the installed app and launch it directly.

### 3. Link an AI assistant

The first time the dashboard connects to the local engine it detects which AI CLIs are installed and asks you to pick one. The choice is saved in `scripts/meta-ralph/config.json`.

Supported options:

- `kimi` — Kimi Code CLI
- `claude` — Claude Code CLI
- `cursor-agent` / `agent` — Cursor agent CLI
- `codex` — Codex CLI
- `OPENAI_API_KEY` — OpenAI-compatible API backend

### 4. Create a ticket and pick a folder

Create a ticket and use **Pick folder** to select the project directory with the native file picker. Because browsers cannot expose absolute paths, you still need to type or confirm the absolute path so the local engine can run `git`, builds, and AI CLIs on that folder.

### 5. Run the factory

Move the ticket to **Ready for Work** and the five-phase loop starts.

## Legacy CLI

The original `meta-ralph` CLI is still available:

```bash
meta-ralph init      # create scripts/meta-ralph/ in the current project
meta-ralph run       # start the multi-agent loop and dashboard
meta-ralph dashboard # start only the web dashboard
meta-ralph status    # show active worker state
meta-ralph stop      # stop active workers and the dashboard
```

## Backend Selection

By default, the backend tries available backends in this order:

```bash
META_RALPH_BACKENDS="kimi claude cursor codex openai_api"
```

Force a backend:

```bash
META_RALPH_BACKEND=claude agenticflow start
META_RALPH_BACKEND=codex agenticflow start
META_RALPH_BACKEND=cursor agenticflow start
META_RALPH_BACKEND=kimi agenticflow start
```

Use a custom runner:

```bash
META_RALPH_BACKEND=custom \
META_RALPH_RUNNER_COMMAND='my-agent --prompt-file "$META_RALPH_PROMPT_FILE"' \
agenticflow start
```

## Skill Recognition

Assistants that support skills should load `SKILL.md` when the user asks for:

- "meta ralph"
- "multi-agent loop"
- "parallel team"
- "MetaGPT workflow"
- "autonomous PRD execution"

If the assistant does not support native skill discovery, use CLI mode.

## Project Layout

```text
meta-ralph/
├── SKILL.md                    # Assistant-facing skill definition
├── README.md                   # This file
├── install.sh                  # Skill and CLI installer
├── assets/
│   └── prd-template.json       # Input PRD template
├── references/
│   ├── metagpt-roles.md        # Role SOPs
│   ├── orchestrator-prompt.md
│   ├── worker-prompt-template.md
│   └── qa-prompt-template.md
├── scripts/
│   ├── meta-ralph.sh           # Main CLI
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

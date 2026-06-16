# Meta-Ralph

Meta-Ralph is a MetaGPT-style multi-agent orchestration skill for AI coding assistants. It coordinates PM Research, Architecture, Planning, parallel Engineers, and QA with a local dashboard for ticket management and live progress.

## What It Does

- Takes a PRD or ticket and executes it through a five-phase loop: PM Analysis -> Architecture -> Planning -> Parallel Execution -> QA Review.
- Supports multiple PM Research agents and Engineer workers, capped by `--max-workers`.
- Gives each Engineer its own role context, feature focus, git worktree, and branch.
- Runs QA before integrating a batch back into trunk.
- Provides a Kanban dashboard at `http://localhost:5050` with live updates.
- Saves per-ticket run snapshots so a ticket can be paused, resumed, or restarted after the dashboard server restarts.

## Installation

### Option 1: Clone Into A Skill Directory

Choose the directory used by your assistant:

```bash
# Kimi
git clone https://github.com/fabricciotc/meta-ralph.git ~/.kimi-code/skills/meta-ralph

# Claude
git clone https://github.com/fabricciotc/meta-ralph.git ~/.claude/skills/meta-ralph

# Cursor
git clone https://github.com/fabricciotc/meta-ralph.git ~/.cursor/skills/meta-ralph

# Codex
git clone https://github.com/fabricciotc/meta-ralph.git ~/.codex/skills/meta-ralph
```

### Option 2: Use The Installer

```bash
git clone https://github.com/fabricciotc/meta-ralph.git
cd meta-ralph
./install.sh
```

The installer:

1. Registers the skill in available assistant skill directories.
2. Creates a Python virtual environment for the dashboard in `dashboard/.venv`.
3. Installs `dashboard/requirements.txt`.
4. Creates a `meta-ralph` command in your PATH.
5. Reports which AI backends are available.

Restart your terminal or run `source ~/.zshrc`, `source ~/.bashrc`, or `source ~/.bash_profile` so the command is available.

## Requirements

- Python 3.10+
- Git
- At least one AI runner:
  - `kimi`
  - `claude`
  - `cursor`
  - `codex`
  - `OPENAI_API_KEY` for OpenAI-compatible API mode
- A modern browser for the dashboard

## Usage

Inside a git project:

```bash
meta-ralph init      # create scripts/meta-ralph/ in the current project
meta-ralph run       # start the multi-agent loop and dashboard
meta-ralph dashboard # start only the dashboard
meta-ralph status    # show active workers
meta-ralph stop      # stop workers and dashboard
```

Then open `http://localhost:5050` and create or move tickets into the work queue.

## Backend Selection

By default, CLI mode tries available backends in this order:

```bash
META_RALPH_BACKENDS="kimi claude cursor codex openai_api"
```

Force a backend:

```bash
META_RALPH_BACKEND=claude meta-ralph run
META_RALPH_BACKEND=codex meta-ralph run
META_RALPH_BACKEND=cursor meta-ralph run
META_RALPH_BACKEND=kimi meta-ralph run
```

Use a custom runner:

```bash
META_RALPH_BACKEND=custom \
META_RALPH_RUNNER_COMMAND='my-agent --prompt-file "$META_RALPH_PROMPT_FILE"' \
meta-ralph run
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

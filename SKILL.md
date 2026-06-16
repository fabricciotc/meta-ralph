---
name: meta-ralph
description: "MetaGPT-style multi-agent autonomous coding loop for AI coding assistants. Orchestrates Product Manager research agents, Architect, Project Manager, parallel Engineer workers with role context and feature focus, and QA review to implement PRDs end-to-end. Use when: user asks for meta ralph, multi-agent loop, parallel team execution, metagpt-style workflow, or autonomous implementation. Do NOT load for: simple one-shot tasks, planning-only work, or tasks requiring continuous human approval."
description-en: "MetaGPT-style multi-agent autonomous coding loop for AI coding assistants. Orchestrates Product Manager research agents, Architect, Project Manager, parallel Engineer workers with role context and feature focus, and QA review to implement PRDs end-to-end. Use when: user asks for meta ralph, multi-agent loop, parallel team execution, metagpt-style workflow, or autonomous implementation. Do NOT load for: simple one-shot tasks, planning-only work, or tasks requiring continuous human approval."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Shell", "Agent", "Task", "TaskOutput", "TaskList", "TaskStop"]
user-invocable: true
disable-model-invocation: false
---

# Meta-Ralph: MetaGPT Multi-Agent Orchestrator

Meta-Ralph combines the MetaGPT method of specialized roles and SOPs with the Ralph autonomous loop pattern. It coordinates product research, architecture, planning, parallel implementation, QA review, and integration while keeping a local Kanban dashboard in sync.

This skill is designed to be assistant-neutral. It can be installed as a skill or prompt bundle for Kimi, Claude, Cursor, or Codex, and its CLI runner can fall back across available AI backends.

## When To Use This Skill

- The user asks for "meta ralph", a multi-agent loop, a parallel team, a MetaGPT-style workflow, or autonomous PRD execution.
- The task is a large PRD with many user stories or tickets.
- The work benefits from specialized roles: Product Manager, Architect, Project Manager, Engineers, and QA.
- Parallel workers are useful and safe for the repository.

## Do Not Use When

- The task is a simple one-shot request.
- The user only wants planning and no implementation.
- The user requires continuous human approval before each action.

## Role Architecture

```text
Orchestrator (meta-ralph)
├── PM Research Agents (1..N)  -> research project areas and domain assumptions
├── Product Manager            -> consolidates findings and decomposes the PRD
├── Architect                  -> defines patterns, contracts, and conventions
├── Project Manager            -> builds dependency-aware batches
├── Engineer Workers (1..N)    -> implement in isolated git worktrees
└── QA Engineer                -> reviews each batch before integration
```

## Usage Modes

### Native Skill Mode

Inside a supported assistant, mention the skill:

- "implement this with meta-ralph"
- "use meta-ralph for this PRD"
- "run the multi-agent loop"

The assistant should act as the Orchestrator and use the child-agent primitive available in the host:

| Host | Preferred primitive | Fallback |
|------|---------------------|----------|
| Cursor | `Subagent` with background execution | `best-of-n-runner` or CLI mode |
| Kimi | `Agent` plus task output polling | CLI mode |
| Claude | `Task` or subagent-style delegation where available | CLI mode |
| Codex | Native agent delegation where available | CLI mode |
| Any host without child agents | CLI mode | Sequential batches with worktree isolation |

If the host does not support background child agents, reduce `MAX_WORKERS` or run batches sequentially while preserving the same PRD, worktree, and QA gates.

### Autonomous CLI Mode

Install the command:

```bash
./install.sh
source ~/.zshrc  # or ~/.bashrc / ~/.bash_profile
```

Then run it inside any git project:

| Command | Action |
|---------|--------|
| `meta-ralph init` | Create `scripts/meta-ralph/` in the current project |
| `meta-ralph run` | Run the 5-phase loop and start the dashboard at `http://localhost:5050` |
| `meta-ralph run --max-workers 10` | Limit parallel workers to 10 |
| `meta-ralph run --skip-pm` | Skip phase 1 and use an existing `prd-expanded.json` |
| `meta-ralph run --skip-architect` | Skip phase 2 and use an existing `architecture.md` |
| `meta-ralph run --skip-planner` | Skip phase 3 and use an existing `execution-plan.json` |
| `meta-ralph run --no-dashboard` | Do not start the web dashboard |
| `meta-ralph dashboard` | Start only the web dashboard |
| `meta-ralph dashboard --port 8080` | Start the dashboard on a custom port |
| `meta-ralph status` | Show active worker state |
| `meta-ralph stop` | Stop active workers and the dashboard |

## Backend Selection

CLI mode tries AI backends in this order unless configured otherwise:

```bash
export META_RALPH_BACKENDS="kimi claude cursor codex openai_api"
export META_RALPH_BACKEND=auto
```

Use one backend explicitly:

```bash
META_RALPH_BACKEND=claude meta-ralph run
META_RALPH_BACKEND=codex meta-ralph run
META_RALPH_BACKEND=cursor meta-ralph run
```

For unsupported or custom CLIs, provide a command. The prompt is exposed through `META_RALPH_PROMPT` and `META_RALPH_PROMPT_FILE`:

```bash
META_RALPH_BACKEND=custom \
META_RALPH_RUNNER_COMMAND='my-agent --prompt-file "$META_RALPH_PROMPT_FILE"' \
meta-ralph run
```

## Web Dashboard

`meta-ralph` includes a local Kanban board at `http://localhost:5050`.

### Board Columns

| Column | Meaning | Actor |
|--------|---------|-------|
| **Backlog** | Tickets or stories waiting for analysis | User / Product Manager |
| **In Design** | PM Research Agents are investigating requirements | PM Research Agents |
| **In Progress** | Engineers are implementing the task | Engineer workers |
| **In Review** | QA is reviewing the batch | QA Engineer |
| **Done** | Task is approved and integrated | None |

### Features

- **Live progress**: the board updates through WebSocket while agents work.
- **Ticket creation**: create tickets from the dashboard; new tickets enter Backlog.
- **Drag and drop**: move tickets between columns; the Orchestrator respects external state changes.
- **Stats**: total, active, done, and blocked counters.

The source of truth is `scripts/meta-ralph/state/board.json`.

## Five-Phase Flow

### Phase 1: PM Analysis

Input: `prd.json` -> Output: `prd-expanded.json`

- The Orchestrator launches PM Research Agents for project areas, domain questions, or components.
- Each PM agent documents findings, risks, implicit requirements, and design options.
- The Product Manager consolidates findings and expands stories into granular technical tasks.
- Each task includes `id`, `title`, `description`, `acceptanceCriteria[]`, `dependencies[]`, `effort`, and `affectedAreas[]`.

### Phase 2: Architecture

Input: `prd-expanded.json` -> Output: `architecture.md`

- The Architect defines technical patterns, APIs, directory structure, and conventions.
- The focus is global and reusable guidance, not task implementation.

### Phase 3: Planning And Dispatch

Input: `prd-expanded.json` + `architecture.md` -> Output: `execution-plan.json`

- The Project Manager builds a dependency DAG.
- Independent tasks are grouped into batches of at most N workers.
- The execution order is explicit and dependency-aware.

### Phase 4: Parallel Execution

Input: `execution-plan.json`

- For each batch:
  1. Spawn Engineer workers using the host's child-agent primitive when available.
  2. Give each worker a specific role, area context, and feature focus.
  3. Each worker implements in an isolated git worktree.
  4. Poll or collect child-agent output until all workers finish.
  5. QA reviews the full batch: combined diffs, tests, and acceptance criteria.
  6. If QA approves, integrate the batch and destroy worktrees.
  7. If QA rejects, retry individual workers or replan.
- Update `progress.txt` after each batch.

### Phase 5: Integration And Close

- Verify the complete PRD.
- Generate a consolidated report.
- Mark `prd.json` complete and emit `COMPLETE`.

## Project Structure

```text
scripts/meta-ralph/
├── prd.json              # Source of truth, edited by the user
├── prd-expanded.json     # Generated by the Product Manager
├── architecture.md       # Generated by the Architect
├── execution-plan.json   # Generated by the Project Manager
├── progress.txt          # Execution log
├── archive/              # Previous runs
└── state/
    ├── board.json        # Kanban dashboard state
    ├── pm-research/      # PM Research notes
    ├── workers/          # Worker metadata
    └── batches/          # Batch results
```

## Golden Rules

1. **One agent, one role**. Do not mix PM, Architect, Engineer, and QA responsibilities in one prompt.
2. **Use parallel PM research when useful**. Research agents should investigate separate areas, then consolidate before writing `prd-expanded.json`.
3. **Every Engineer has context**. Each worker gets a role context, area context, and feature focus; avoid generic workers.
4. **Isolate workers**. Each Engineer works in a dedicated git worktree and branch.
5. **Integrate only after QA**. Never merge to trunk without QA approval.
6. **Cap parallelism**. Default max workers is 20, but reduce it for rate limits, small batches, or hosts without background agents.
7. **Replan intelligently**. If QA rejects a batch, the Project Manager chooses individual retry, replan, or escalation.
8. **Keep `board.json` synchronized**. The dashboard must reflect real ticket state.
9. **Update local agent instructions**. If durable project patterns are discovered, update the appropriate `AGENTS.md` or skill instruction files.

## Detailed References

- Role SOPs: [`references/metagpt-roles.md`](references/metagpt-roles.md)
- Engineer prompt template: [`references/worker-prompt-template.md`](references/worker-prompt-template.md)
- QA prompt template: [`references/qa-prompt-template.md`](references/qa-prompt-template.md)
- Orchestrator prompt: [`references/orchestrator-prompt.md`](references/orchestrator-prompt.md)
- Dashboard: [`dashboard/`](dashboard/)
- PRD format: [`assets/prd-template.json`](assets/prd-template.json)

## Safety

- All scripts execute local code. Review the PRD before running.
- Avoid host-specific full-auto flags unless you understand their permission model.
- Work on a dedicated branch, usually `meta-ralph/*`.
- Keep commits small enough for QA to review each batch.

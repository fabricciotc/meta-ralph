# Meta-Ralph Backend MetaGPT Design

## Summary

The backend models a local software factory: a ticket moves through PM analysis, architecture, planning, implementation, QA, and completion. Each phase updates runtime state that the dashboard can render.

## Components

- Board state: stores tickets and Kanban columns.
- Run state: stores active phase, progress, agents, logs, messages, and pending decisions.
- Orchestrator: coordinates roles and phase transitions.
- Role layer: encapsulates PM, Architect, Project Manager, Engineer, and QA behavior.
- Runner registry: selects the configured AI backend.
- Dashboard API: exposes board, run-state, logs, restart, and system info.

## State Model

The backend stores generated artifacts under `scripts/meta-ralph`:

- `prd.json`
- `prd-expanded.json`
- `architecture.md`
- `execution-plan.json`
- `progress.txt`
- `state/board.json`
- `state/workers/*.json`
- `state/batches/*.json`

## Guardrails

- The Orchestrator does not implement code directly.
- Engineer workers use isolated worktrees.
- QA must approve before integration.
- Runtime cleanup must not delete user source code.

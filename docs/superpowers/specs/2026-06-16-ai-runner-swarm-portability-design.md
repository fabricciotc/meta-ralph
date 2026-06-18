# AI Runner Swarm Portability Design

## Problem

AgenticFlow originally assumed one assistant CLI and one child-agent API. Publication requires a neutral design that works across multiple AI coding assistants.

## Design

### Native Skill Mode

The host assistant can run the AgenticFlow backend and use its own child-agent primitive when available:

- Cursor: `Subagent` or equivalent background worker support.
- Kimi: `Agent` and task output polling.
- Claude: `Task` or subagent-style delegation when available.
- Codex: native delegation when available.

If no child-agent primitive exists, the host should run phases sequentially while preserving role boundaries.

### CLI Mode

The AgenticFlow command builds the Orchestrator prompt, starts the dashboard, and sends the prompt to a configured backend.

Backend selection is controlled by:

- `AGENTICFLOW_BACKEND`
- `AGENTICFLOW_BACKENDS`

## Safety

- Never hide backend failure.
- Preserve worktree isolation regardless of backend.
- Keep QA gates mandatory.
- Keep all user-facing docs in English.

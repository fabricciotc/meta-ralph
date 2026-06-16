# AI Runner Swarm Portability Design

## Problem

Meta-Ralph originally assumed one assistant CLI and one child-agent API. Publication requires a neutral design that works across multiple AI coding assistants.

## Design

### Native Skill Mode

The host assistant reads `SKILL.md` and acts as the Orchestrator. It should use its own child-agent primitive when available:

- Cursor: `Subagent` or equivalent background worker support.
- Kimi: `Agent` and task output polling.
- Claude: `Task` or subagent-style delegation when available.
- Codex: native delegation when available.

If no child-agent primitive exists, the host should run phases sequentially while preserving role boundaries.

### CLI Mode

The `meta-ralph` command builds the Orchestrator prompt, starts the dashboard, and sends the prompt to a configured backend.

Backend selection is controlled by:

- `META_RALPH_BACKEND`
- `META_RALPH_BACKENDS`
- `META_RALPH_RUNNER_COMMAND`
- `META_RALPH_PROMPT`
- `META_RALPH_PROMPT_FILE`

### Custom Runner Contract

Custom runners receive the full prompt through:

- `META_RALPH_PROMPT`
- `META_RALPH_PROMPT_FILE`

The command should exit `0` on success and non-zero on failure.

## Safety

- Never hide backend failure.
- Preserve worktree isolation regardless of backend.
- Keep QA gates mandatory.
- Keep all user-facing docs in English.

# AI Runner Swarm Portability Plan

## Goal

Make AgenticFlow portable across Kimi, Claude, Cursor, Copilot, Codex, and OpenAI-compatible API runners.

## Strategy

- Keep the app and backend configuration assistant-neutral.
- Treat each assistant CLI as a backend adapter.
- Prefer native child-agent primitives when the host provides them.
- Fall back to CLI mode or sequential execution when child agents are unavailable.
- Expose backend selection through environment variables.

## Backend Order

Default order:

```bash
AGENTICFLOW_BACKENDS="kimi claude cursor copilot codex openai_api"
```

Explicit backend:

```bash
AGENTICFLOW_BACKEND=claude agenticflow start
```

## Acceptance Criteria

- The CLI no longer hardcodes one AI provider.
- Documentation explains app and CLI mode consistently.
- A missing backend produces a clear error and a configurable fallback path.
- Host-specific commands are isolated behind backend adapter logic.

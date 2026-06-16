# AI Runner Swarm Portability Plan

## Goal

Make Meta-Ralph portable across Kimi, Claude, Cursor, Codex, OpenAI-compatible API runners, and custom CLI runners.

## Strategy

- Keep `SKILL.md` assistant-neutral.
- Treat each assistant CLI as a backend adapter.
- Prefer native child-agent primitives when the host provides them.
- Fall back to CLI mode or sequential execution when child agents are unavailable.
- Expose backend selection through environment variables.

## Backend Order

Default order:

```bash
META_RALPH_BACKENDS="kimi claude cursor codex openai_api"
```

Explicit backend:

```bash
META_RALPH_BACKEND=claude meta-ralph run
```

Custom backend:

```bash
META_RALPH_BACKEND=custom \
META_RALPH_RUNNER_COMMAND='my-agent --prompt-file "$META_RALPH_PROMPT_FILE"' \
meta-ralph run
```

## Acceptance Criteria

- The CLI no longer hardcodes one AI provider.
- Documentation explains native skill mode and CLI mode separately.
- A missing backend produces a clear error and a configurable fallback path.
- Host-specific commands are isolated behind backend adapter logic.

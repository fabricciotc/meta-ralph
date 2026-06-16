# Dashboard Auto-Resume Plan

## Goal

Allow the dashboard to recover useful run context after a server restart or ticket switch.

## Scope

- Persist run-state snapshots per ticket.
- Load the latest snapshot when a ticket is resumed.
- Rebuild visible agent cards, logs, pending decisions, and progress summary from saved state.
- Avoid restarting work automatically unless the user explicitly starts or resumes the ticket.

## Implementation Notes

- Store snapshots next to other Meta-Ralph state files.
- Use ticket ID as the lookup key.
- Treat snapshots as runtime metadata, not source of truth for code.
- If a snapshot is corrupt, fail gracefully and show a clear message.

## Acceptance Criteria

- A paused ticket can be resumed after the dashboard server restarts.
- Logs and agent state reappear after reload.
- Auto-resume never deletes code or rewrites git state.

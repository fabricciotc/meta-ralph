# Ticket Restart Plan

## Goal

Allow a ticket run to be restarted cleanly from the dashboard without deleting user code changes in the repository.

## Scope

- Clear the ticket runtime state, snapshots, generated PRD artifacts, architecture output, execution plan, and worker metadata for the selected ticket.
- Preserve repository code changes and git history.
- Keep the board ticket visible and return it to a restartable state.
- Add a confirmation flow in the dashboard before destructive run-state cleanup.

## Implementation Notes

- Restart is a runtime operation, not a repository reset.
- The dashboard should call a dedicated backend endpoint for restart.
- The backend should remove per-ticket run-state files and generated artifacts associated with that ticket.
- Any active runner for the ticket must be stopped before cleanup starts.
- The UI should refresh board state, run state, and logs after restart.

## Acceptance Criteria

- Restarting a ticket does not delete source code changes.
- The dashboard shows a clear confirmation prompt.
- The ticket can be started again after restart.
- Stale agent logs and generated planning artifacts do not leak into the new run.

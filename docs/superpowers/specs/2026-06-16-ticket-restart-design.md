# Ticket Restart Design

## Summary

Ticket restart resets orchestration artifacts for a single ticket while preserving repository code and user-authored files.

## Backend Design

- Add a restart endpoint that receives a ticket ID.
- Stop any active runner for that ticket.
- Delete ticket-specific run-state snapshots, prompt/output captures, generated PRD files, planning files, worker state, and batch state when they belong to the ticket.
- Keep `board.json` and reset the ticket status to a work-ready state.
- Append a clear log entry describing the restart.

## Frontend Design

- Show a confirmation modal before restart.
- Explain that generated run artifacts will be removed but code changes will remain.
- Refresh ticket detail, run-state, and logs after the backend completes.

## Safety Rules

- Never run `git reset`, `git clean`, or branch deletion from restart.
- Never remove repository files outside `scripts/meta-ralph/state` and generated Meta-Ralph artifacts.
- If a runner cannot be stopped, fail safely and report the reason.

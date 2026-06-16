# Meta-Ralph Backend Phase 1 Core Plan

## Goal

Create the initial backend foundation for the dashboard-driven Meta-Ralph runner.

## Scope

- Maintain board state in JSON.
- Expose HTTP endpoints for tickets, run-state, logs, and system information.
- Start and stop a runner for a selected ticket.
- Persist enough runtime state to inspect progress from the dashboard.
- Keep the implementation local-first and simple to run.

## Deliverables

- Dashboard server entry point.
- Board load/save helpers.
- Run-state persistence.
- Ticket lifecycle endpoints.
- Basic runner thread that can execute the orchestration flow.

## Acceptance Criteria

- The dashboard can load and update tickets.
- A ticket can trigger a run.
- Logs and agent state are visible while the run progresses.
- State survives a server restart when persisted snapshots exist.

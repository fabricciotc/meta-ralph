# Dashboard Redesign Design

## Goal

Provide a clear local dashboard for ticket management, live agent progress, and orchestration logs.

## Layout

- Header with project, model/backend, and run status.
- Kanban board with Backlog, In Design, In Progress, In Review, and Done columns.
- Ticket detail panel with runtime summary.
- Agent activity panel with logs and progress.
- Decision prompt area for rare cases that require user input.

## Interaction Rules

- Dragging a ticket updates `board.json`.
- Starting work on a ticket creates or resumes run-state.
- Restarting a ticket clears generated run artifacts but preserves source code.
- The UI should clearly distinguish ticket state, agent state, and repository state.

## Acceptance Criteria

- The dashboard renders useful status without reading terminal logs.
- Users can create, move, start, pause, resume, and restart tickets.
- Long-running runs remain understandable through logs and agent cards.

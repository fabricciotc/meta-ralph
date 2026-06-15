# Dashboard WTW redesign — design spec

## Goal
Evolve the AgentFlow dashboard from a floating Adaline window into a native web app that uses the WTW logo and brand colors the user already supplied, while keeping a fixed traces panel, a fixed debug footer, and adding a visible ticket-status section plus a messaging feed. The existing Adaline visual style (typography, component shapes, button styling, icons, spacing) is kept; only the color palette and logo change to WTW.

## Brand
- Logo: `static/wtw-logo.svg` (purple WTW wordmark, `#7f35b2`).
- Primary accent: `#7f35b2`.
- Light theme surfaces: keep current light surfaces but replace greenish tints with neutral `#f7f7f9` / `#ffffff` and `rgba(18,18,22,0.08)` borders.
- Text: keep near-black `#111114`, subtle `#5b5b66`, disabled `#8e8e99`.
- Status colors: ok `#0d8a53`, err `#b91c5a`, wrn `#b56d00`, info `#146bb8`.
- Debug footer: keep dark footer style (`#161618` background, `#eaeaed` text).

## Layout (native app, full viewport)
```
┌─────────────────────────────────────────────────────────────┐
│  Header (fixed, 52 px)                                      │
│  [WTW logo + name]  [Modelo Status Ticket Conn] [Btns]     │
├─────────────────────────────────────────────────────────────┤
│  Run bar (collapsible) — ticket id, progress, elapsed,     │
│  running agents count                                       │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  Traces  │  Graph (agents)                                  │
│  panel   │                                                  │
│  (fixed  │──────────────────────────────────────────────────│
│   left,  │  Ticket status    │  Messaging feed              │
│  ~320 px)│  (40 %)           │  (60 %)                      │
│          │                                                  │
├──────────┴──────────────────────────────────────────────────┤
│  Debug footer (fixed, ~140 px)                               │
└─────────────────────────────────────────────────────────────┘
```

- **Header**: native navbar, not a window titlebar. Left: WTW logo + "AgentFlow" + tagline. Center: pills for Model, Status, Ticket, Connection. Right: Tickets, New, theme toggle buttons.
- **Run bar**: below header. Shows active ticket id, status badge, progress bar, elapsed time, and count of running agents. Collapses to a single compact line when idle.
- **Traces panel**: fixed left column, same role as today. Header with "Traces" title and live badge. Scrollable list of trace items with time, agent name, message, duration, tokens.
- **Graph**: occupies the upper-right area. Same node/edge behavior as today, uses WTW primary color for active/hover accents.
- **Ticket status panel**: lower-left of the right area. Shows selected/active ticket details, current phase, agent statuses, and key metrics (duration, tokens).
- **Messaging feed**: lower-right of the right area. Lists agent-to-agent messages with from → to, timestamp, question and answer.
- **Debug footer**: fixed bottom, dark theme. Logs with info/success/warning/error levels.

## Components & interactions
- **Theme toggle**: switches light/dark via body class. Dark theme uses `#0c0c0e` background, `#1a1a1d` surfaces, purple `#9f5fd1` for primary highlights.
- **Trace item**: click selects the agent and filters debug logs (existing behavior preserved).
- **Graph node**: click toggles selection and filters debug logs.
- **Ticket row in traces/sidebar**: click selects the ticket and updates the Ticket status panel. (If ticket list remains in modal, no new sidebar list is required; traces panel is enough.)
- **Messaging feed**: auto-scrolls to newest message; shows pending answers in muted style.
- **Modals**: existing tickets/ticket/question/design-review/confirm modals remain; styled with WTW palette.

## Accessibility
- All interactive elements keyboard-focusable.
- Color not used alone for status (icons + text).
- Contrast ratios >= 4.5:1 for text.

## Data
No new backend endpoints. Reuses:
- `GET /api/traces`
- `GET /api/graph`
- WebSocket `run_state` for live state, messages, questions, design reviews.
- Existing ticket REST endpoints.

## Scope
- Modify `static/index.html`, `static/style.css`, `static/app.js` only.
- Backend (`server.py`, etc.) unchanged.

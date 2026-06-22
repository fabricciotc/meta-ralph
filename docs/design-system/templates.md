# AgenticFlow — Basic UX Templates & Design System Handoff

> Role: UX Designer pre-engineering squad  
> Source of truth: `DESIGN.md` (project root)  
> Target audience: Engineers implementing dashboard / frontend features.

---

## 1. Research & Inspiration

The goal was to find agent-readable design systems and real-product references that match a **dense, developer-first command center** for autonomous software engineering.

### References reviewed

| Source | What it offered | How it influenced AgenticFlow |
|--------|-----------------|-------------------------------|
| [styles.refero.design](https://styles.refero.design/) | 2,000+ AI-readable `DESIGN.md` examples extracted from leading product websites (Linear, Mercury, Vercel, Duolingo, Apple, etc.) | Confirmed the value of YAML + Markdown design tokens, semantic color roles, and component rules for agents. |
| [Linear @ Refero](https://styles.refero.design/style/90ce5883-bb24-4466-93f7-801cd617b0d1) | Midnight command deck, obsidian surfaces, acid-lime single accent, hairline borders, instrument-panel density. | Inspired the "one accent color" rule, the near-flat elevation model, and the use of mono for technical metadata. |
| [Mercury @ Refero](https://styles.refero.design/) | Mountain-top command center, high-contrast status pills, modular panels. | Reinforced the header-pill live-state pattern and modular three-column layout. |
| [Vercel @ Refero](https://styles.refero.design/) | Prismatic monolith, clean surface hierarchy, restrained brand usage. | Supported the decision to keep WTW purple as the only chromatic brand accent. |
| [Google Stitch `DESIGN.md` spec](https://github.com/google-labs-code/design.md) | Official agent-readable design system format with YAML frontmatter and Markdown body. | Dictated the structure of `DESIGN.md`. |
| [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | Curated `DESIGN.md` files by popular brand design systems. | Provided the template sections (visual theme, tokens, components, do's/don'ts, agent prompt guide). |

### Key takeaways

1. **Agents need tokens + prose.** JSON tokens are not enough; Markdown rationale explains *when* and *why* to use a value.
2. **One accent is enough.** Linear's acid-lime and Vercel's neutral brand usage both prove that a single color can carry an entire UI.
3. **Elevation = surface + border, not shadow.** Modern dev tools use hairline borders and subtle surface steps instead of heavy shadows.
4. **Monospace is a semantic signal.** Code, IDs, paths, and timestamps should always use a mono font to reduce cognitive load.

---

## 2. Design Decisions for AgenticFlow

### Visual direction

- **Name:** WTW Software Factory Command Center.
- **Mood:** Calm, focused, high-trust, professional.
- **Density:** Compact (like Linear / Mercury), because the dashboard shows many parallel workstreams.
- **Accent:** WTW purple `#7f35b2` only.
- **Themes:** Light and dark share the same structure; only the surface stack swaps.

### Structural layout

```text
┌─────────────────────────────────────────────────────────────┐
│  Header  (brand | path bar | model/status/ticket | actions) │  50px
├─────────────────────────────────────────────────────────────┤
│  Run bar  (ticket | progress | elapsed | agents)            │  34px
├──────────┬───────────────────────────────┬──────────────────┤
│          │                               │                  │
│ Traces   │     Main canvas               │ Chat /           │
│ panel    │     (agent graph + ticket)    │ deliverables     │
│ 320px    │                               │ panel 320px      │
│          │                               │                  │
└──────────┴───────────────────────────────┴──────────────────┘
         ↑ optional debug footer
```

### Component inventory

- Buttons: primary, secondary, ghost, danger, icon, small.
- Header pills: Model, Status, Ticket, Connection.
- Panels: traces, behaviors/graph, ticket status, messaging, deliverables, chat.
- Cards: deliverable items, ticket rows.
- Status badges: idle, running, paused, done, failed.
- Modals: tickets list, ticket editor, confirmation, AI link, design review.
- Inputs / selects / textareas.
- Chat bubbles and typing indicator.
- Agent graph nodes and connection lines.

---

## 3. Basic HTML Templates

These snippets are starting points for new features. They assume the existing `dashboard/static/style.css` custom properties are loaded.

### Button set

```html
<button class="btn btn-primary"><i data-lucide="plus"></i> New ticket</button>
<button class="btn btn-secondary">Cancel</button>
<button class="btn btn-ghost">View logs</button>
<button class="btn btn-danger">Stop run</button>
<button class="btn btn-icon" aria-label="Refresh"><i data-lucide="refresh-cw"></i></button>
<button class="btn btn-primary btn-small">Save</button>
```

### Header pill

```html
<div class="header-pill">
  <span class="pill-label">Status</span>
  <span class="pill-value status-running">Running</span>
</div>
```

### Panel

```html
<aside class="traces-panel" aria-label="Traces">
  <div class="panel-header">
    <span class="panel-title"><i data-lucide="list-tree"></i> Traces</span>
    <span class="badge-live"><span class="live-dot"></span> live</span>
  </div>
  <div class="traces-list">
    <!-- items -->
  </div>
</aside>
```

### Card (deliverable / ticket)

```html
<div class="deliverable-item">
  <div class="deliverable-main">
    <i data-lucide="file-text"></i>
    <div class="deliverable-copy">
      <div class="deliverable-title">architecture.md</div>
      <div class="deliverable-path">state/AF-42/</div>
    </div>
  </div>
  <div class="deliverable-actions">
    <button class="btn btn-icon btn-small" aria-label="Open"><i data-lucide="external-link"></i></button>
  </div>
</div>
```

### Status badge

```html
<span class="run-bar-status running">running</span>
<span class="run-bar-status done">completed</span>
<span class="run-bar-status failed">failed</span>
```

### Modal

```html
<div class="modal open" id="example-modal">
  <div class="modal-content ticket-modal-content">
    <div class="modal-header">
      <div class="modal-header-left">
        <div class="modal-header-icon"><i data-lucide="ticket"></i></div>
        <div>
          <h2>Ticket details</h2>
          <div class="modal-header-subtitle">AF-42 · created 2m ago</div>
        </div>
      </div>
      <button class="btn btn-close" aria-label="Close">×</button>
    </div>
    <div class="modal-body">
      <!-- form or content -->
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost">Cancel</button>
      <button class="btn btn-primary">Save changes</button>
    </div>
  </div>
</div>
```

### Input + select

```html
<input type="text" class="input" placeholder="Ticket title" aria-label="Ticket title">

<select class="input" aria-label="Assign role">
  <option value="engineer">Engineer</option>
  <option value="architect">Architect</option>
  <option value="qa">QA</option>
</select>
```

### Chat message

```html
<div class="chat-message agent">
  <div class="chat-bubble">
    <p>I'll split this PRD into architecture and planning phases.</p>
    <div class="chat-meta">Architect · 14:32</div>
  </div>
</div>
```

### Empty state

```html
<div class="traces-empty">
  <i data-lucide="activity"></i>
  <p>Waiting for runner activity...</p>
</div>
```

---

## 4. Token Quick Reference

Copy these CSS custom properties when extending the stylesheet:

```css
/* Brand */
--wtw-purple: #7f35b2;
--wtw-purple-hover: #662b8e;

/* Surfaces (light) */
--bg: #f7f7f9;
--surface-base: #f7f7f9;
--surface-low: #efeff2;
--surface-high: #ffffff;
--tint-base: rgba(18, 18, 22, 0.08);
--tint-mild: rgba(18, 18, 22, 0.05);
--tint-strong: rgba(18, 18, 22, 0.2);

/* Text (light) */
--on-surface-base: #111114;
--on-surface-base-subtle: #5b5b66;
--on-surface-base-disabled: #8e8e99;

/* Functional */
--primary: var(--wtw-purple);
--primary-hover: var(--wtw-purple-hover);
--ok: #0d8a53;
--err: #b91c5a;
--wrn: #b56d00;
--info: #146bb8;

/* Shapes */
--radius-sm: 6px;
--radius-md: 10px;
--radius-lg: 12px;
```

Dark-mode equivalents are applied via `.dark` on `body`/`html`.

---

## 5. Handoff Notes for the Engineer Squad

### What changed

1. Added a project-level `DESIGN.md` in the repo root.
   - It follows the Google Stitch / Refero `DESIGN.md` format.
   - It contains YAML tokens and Markdown rationale.
   - Any AI coding agent can read it to generate consistent UI.

2. Added this `docs/design-system/templates.md` document.
   - Records the research and decisions.
   - Provides copy-paste HTML templates.

3. Updated `.gitignore`.
   - Ignores .NET build artifacts (`bin/`, `obj/`, `*.dll`).
   - Ignores root `dist/` and coverage/test output.

### How to use these files

- Before building a new dashboard feature, read `DESIGN.md`.
- Use the templates above as starting points.
- When in doubt, follow the existing `dashboard/static/style.css` custom properties.
- Keep WTW purple as the only accent; functional colors are for status only.
- Test both light and dark themes.

### What not to do

- Do not add new accent colors without UX review.
- Do not hard-code hex values; always use the CSS custom properties.
- Do not increase information density beyond the current compact baseline without a usability reason.

---

## 6. Next Steps (post-handoff)

1. Engineering squad reviews `DESIGN.md` and flags any implementation conflicts.
2. Backlog tickets created for:
   - Responsive behavior below 1280px (drawer collapse).
   - Animation / motion tokens (hover, panel transitions, graph node pulses).
   - Accessibility audit (focus states, ARIA, keyboard navigation).
3. Update `DESIGN.md` when new tokens or components are approved.

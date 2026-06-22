---
version: alpha
name: AgenticFlow
brand: WTW Software Factory
description: |
  AgenticFlow is a native desktop command center for a MetaGPT-style multi-agent
  software factory. The interface should feel like a calm, high-trust operations
  deck: dense information, clear hierarchy, and a single accent color (WTW purple)
  that guides attention without shouting. Light and dark themes share the same
  structural language; only the surface stack and contrast curve change.

colors:
  # Brand
  wtw-purple: "#7f35b2"
  wtw-purple-hover: "#662b8e"
  wtw-purple-muted: "rgba(127, 53, 178, 0.08)"

  # Light theme surfaces
  light-bg: "#f7f7f9"
  light-surface-base: "#f7f7f9"
  light-surface-low: "#efeff2"
  light-surface-high: "#ffffff"
  light-tint-base: "rgba(18, 18, 22, 0.08)"
  light-tint-mild: "rgba(18, 18, 22, 0.05)"
  light-tint-strong: "rgba(18, 18, 22, 0.2)"

  # Light theme text
  light-text-primary: "#111114"
  light-text-secondary: "#5b5b66"
  light-text-tertiary: "#8e8e99"

  # Dark theme surfaces
  dark-bg: "#0c0c0e"
  dark-surface-base: "#121214"
  dark-surface-low: "#0c0c0e"
  dark-surface-high: "#1a1a1d"
  dark-tint-base: "rgba(255, 255, 255, 0.08)"
  dark-tint-mild: "rgba(255, 255, 255, 0.05)"
  dark-tint-strong: "rgba(255, 255, 255, 0.16)"

  # Dark theme text
  dark-text-primary: "#f1f1f5"
  dark-text-secondary: "#a6a6b0"
  dark-text-tertiary: "#6e6e78"

  # Functional (theme-agnostic semantic roles)
  primary: "{colors.wtw-purple}"
  primary-hover: "{colors.wtw-purple-hover}"
  primary-muted: "{colors.wtw-purple-muted}"
  success: "#0d8a53"
  success-muted: "rgba(13, 138, 83, 0.1)"
  warning: "#b56d00"
  warning-muted: "rgba(181, 109, 0, 0.1)"
  danger: "#b91c5a"
  danger-hover: "#931548"
  danger-muted: "rgba(185, 28, 90, 0.1)"
  info: "#146bb8"
  info-muted: "rgba(20, 107, 184, 0.1)"

typography:
  sans:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    role: "All UI text, headings, body, buttons, labels"
  mono:
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
    role: "Code snippets, IDs, paths, timestamps, technical metadata"
  scale:
    micro:
      fontSize: 0.55rem
      lineHeight: 1.0
      letterSpacing: 0.08em
      textTransform: uppercase
    caption:
      fontSize: 0.72rem
      lineHeight: 1.4
    body:
      fontSize: 0.85rem
      lineHeight: 1.5
    body-lg:
      fontSize: 0.95rem
      lineHeight: 1.55
    subheading:
      fontSize: 1.05rem
      lineHeight: 1.3
      fontWeight: 600
    heading-sm:
      fontSize: 1.25rem
      lineHeight: 1.25
      fontWeight: 700
    heading:
      fontSize: 1.5rem
      lineHeight: 1.2
      fontWeight: 700

spacing:
  base: 4px
  scale:
    xs: 4px
    sm: 8px
    md: 12px
    lg: 16px
    xl: 24px
    2xl: 32px
    3xl: 48px

radii:
  sm: 6px
  md: 10px
  lg: 12px
  pill: 9999px

shadows:
  sm: "0 1px 2px rgba(0, 0, 0, 0.04)"
  window-light: "0 1px 0 0 rgba(255, 255, 255, 0.9) inset, 0 12px 32px -16px rgba(0, 0, 0, 0.18), 0 4px 10px -4px rgba(0, 0, 0, 0.1)"
  window-dark: "0 1px 0 0 rgba(255, 255, 255, 0.06) inset, 0 16px 40px -18px rgba(0, 0, 0, 0.55), 0 5px 14px -6px rgba(0, 0, 0, 0.45)"
---

## Overview

AgenticFlow's visual identity is "command center for autonomous engineering." The UI borrows density and hierarchy from developer-first tools like Linear and Mercury, but keeps a professional, enterprise-friendly tone through WTW purple as the sole chromatic accent.

### Design philosophy

- **Information density over whitespace.** The dashboard shows many parallel workstreams (traces, agents, chat, deliverables). Every pixel should carry signal.
- **One accent to rule them all.** WTW purple is the only strong color used for primary actions, active states, and brand moments. Functional colors (success/warning/danger/info) are reserved for status.
- **Light and dark as siblings.** Both themes use the same spacing, radii, and component shapes. Only the surface stack and text contrast curve swap.
- **Monospace for metadata.** Paths, ticket IDs, timestamps, and agent names use JetBrains Mono to visually separate machine-readable data from prose.

### Inspiration references

- **Linear** (refero.style): midnight command deck, acid-lime accent on obsidian, instrument-panel density, hairline borders.
- **Mercury** (refero.style): mountain-top command center, high-contrast status pills, modular panels.
- **Vercel** (refero.style): prismatic monolith, clean surface hierarchy, restrained brand color usage.
- **Google Stitch DESIGN.md spec**: YAML-frontmatter + Markdown format for agent-readable design systems.
- **VoltAgent/awesome-design-md**: curated collection of agent-readable design system documents extracted from real products.

## Colors

### Surfaces

| Token | Light | Dark | Role |
|-------|-------|------|------|
| `bg` | `#f7f7f9` | `#0c0c0e` | App canvas, behind all panels |
| `surface-base` | `#f7f7f9` | `#121214` | Default panel background |
| `surface-low` | `#efeff2` | `#0c0c0e` | Subtle recessed surfaces, input backgrounds |
| `surface-high` | `#ffffff` | `#1a1a1d` | Header, elevated cards, modal shells |
| `tint-base` | `rgba(18,18,22,0.08)` | `rgba(255,255,255,0.08)` | Borders, dividers |
| `tint-mild` | `rgba(18,18,22,0.05)` | `rgba(255,255,255,0.05)` | Hover washes |
| `tint-strong` | `rgba(18,18,22,0.2)` | `rgba(255,255,255,0.16)` | Strong separators |

### Text

| Token | Light | Dark | Role |
|-------|-------|------|------|
| `text-primary` | `#111114` | `#f1f1f5` | Headings, primary content |
| `text-secondary` | `#5b5b66` | `#a6a6b0` | Captions, metadata |
| `text-tertiary` | `#8e8e99` | `#6e6e78` | Disabled, placeholders |

### Functional

| Token | Value | Role |
|-------|-------|------|
| `success` | `#0d8a53` | Completed, healthy, online |
| `warning` | `#b56d00` | Paused, queued, attention needed |
| `danger` | `#b91c5a` | Failed, error, destructive action |
| `info` | `#146bb8` | Running, active, in-progress |
| `primary` | `#7f35b2` | Primary actions, brand accent, selected states |

## Typography

- **Sans:** Inter for all interface text. Weights 400, 500, 600, 700.
- **Mono:** JetBrains Mono for code, IDs, paths, timestamps.
- **Uppercase + letter-spacing** for micro labels (status, pill labels, run-bar tags).
- **Tight leading** on captions and metadata to keep lists compact.

### Type roles

| Role | Size | Weight | Usage |
|------|------|--------|-------|
| `micro` | 0.55rem | 600 uppercase | Pill labels, run-bar tags, badges |
| `caption` | 0.72rem | 400 | Metadata, timestamps, paths |
| `body` | 0.85rem | 400 | Body text, chat messages, ticket descriptions |
| `body-lg` | 0.95rem | 400 | Modal body, readable paragraphs |
| `subheading` | 1.05rem | 600 | Panel titles, section headers |
| `heading-sm` | 1.25rem | 700 | Modal titles |
| `heading` | 1.5rem | 700 | Page-level headings |

## Layout & Spacing

- **Base grid:** 4px.
- **Panel gutters:** 0.75rem (12px) internal padding.
- **Element gaps:** 0.5rem (8px) for related items, 0.75rem (12px) for groups.
- **Header height:** 50px.
- **Run bar height:** 34px.
- **Side panels:** 320px default, min 280px, max 420px.
- **Respect `overflow: hidden` on the app shell;** panels scroll internally.

## Elevation & Depth

Elevation is communicated through surface color and hairline borders, not heavy shadows.

- **Level 0:** `bg` — canvas.
- **Level 1:** `surface-base` — side panels.
- **Level 2:** `surface-high` — header, run bar, cards, modals.
- **Borders:** `tint-base` 1px for separation; `tint-strong` for strong dividers.
- **Window shadow:** Only the native desktop window uses a soft directional shadow. In-app cards use near-flat 1px borders.

## Shapes

| Element | Radius |
|---------|--------|
| Buttons | 6px |
| Inputs / selects | 6px |
| Cards / panels | 10–12px |
| Status pills / progress track | 9999px |
| Modal shells | 12px |
| Icons in header | 6px hover background |

## Components

### Buttons

- **Primary:** `wtw-purple` background, white text, 6px radius, padding `0.5rem 0.9rem`. Hover to `wtw-purple-hover`.
- **Secondary:** `surface-low` background, `text-primary`, 1px `tint-base` border. Hover: `tint-mild` wash.
- **Ghost:** transparent, `text-secondary`. Hover: `tint-mild` wash, `text-primary`.
- **Danger:** `danger` background, white text. Hover to `danger-hover`.
- **Icon:** 32×32px square, transparent, `text-secondary`, 6px radius. Hover: `tint-mild`.
- **Small variant:** reduce font-size to 0.8rem and padding to `0.35rem 0.65rem`.

### Header pills

Small stacked labels used for live state (Model, Status, Ticket, Connection). `surface-base` background, `tint-base` border, 6px radius. Label is `micro`; value is `caption` in mono.

### Panels

- `surface-base` background.
- 1px `tint-base` border on the separating edge (right for left panel, left for right panel).
- Panel header: flex row, `space-between`, icon + title on left, badge/actions on right.
- Live badge: small dot + "live" text in `info` or `success`.

### Cards (deliverables, tickets)

- `surface-high` background.
- 1px `tint-base` border, 10–12px radius.
- Padding 0.55rem for dense items, 1rem for readable content cards.
- Hover: subtle `tint-mild` wash or left-edge `primary` 3px accent.

### Status badges

Use `pill` radius and muted functional background with matching text color:

| State | Background | Text |
|-------|------------|------|
| idle / queued | `tint-mild` | `text-tertiary` |
| running / in-progress | `info-muted` | `info` |
| paused | `warning-muted` | `warning` |
| done / completed | `success-muted` | `success` |
| failed | `danger-muted` | `danger` |

### Modals

- Full viewport overlay with translucent dark scrim.
- Content shell: `surface-high`, 12px radius, `window` shadow.
- Header: title + subtitle on left, close/action buttons on right.
- Body: max readable width; use `body-lg` for explanations.
- Actions: right-aligned, primary action last.

### Inputs and selects

- `surface-high` background, 1px `tint-base` border, 6px radius.
- Focus: `primary` outline or border.
- Placeholder: `text-tertiary`.
- Monospace for path/ID inputs.

### Chat

- Messages stack vertically with 0.6rem gap.
- User bubbles: `surface-high` or subtle `primary-muted` tint.
- Agent bubbles: `surface-base` with 1px `tint-base` border.
- Meta line: `caption` in `text-secondary`.
- Typing indicator: dot-matrix loader in `text-secondary`.

### Traces / agent graph

- Nodes sit on a subtle grid or SVG connection layer.
- Node states: default `surface-high`, running `info-muted`, success `success-muted`, error `danger-muted`.
- Connection lines: `tint-strong` with directional arrow markers.

## Do's and Don'ts

### Do

- Use WTW purple sparingly for the single primary action on a screen.
- Keep side panels at fixed widths; let the center canvas absorb resize.
- Use mono for any path, ID, timestamp, or technical value.
- Provide empty states with a clear next action.
- Support both light and dark themes from day one.
- Maintain WCAG AA contrast for all text on surfaces.

### Don't

- Add a second accent color competing with WTW purple.
- Use heavy drop shadows inside the app; rely on surface + border.
- Stretch buttons full-width unless in a narrow modal.
- Use pure black or pure white; the palette uses off-black/off-white to reduce eye strain.
- Mix theme tokens (e.g. dark surfaces in light mode).

## Dark Theme

Apply a `.dark` class on `html` or `body`. CSS custom properties should swap to dark values. All components consume the same semantic tokens (`bg`, `surface-high`, `text-primary`, etc.), so no component-level overrides are needed.

## Agent Prompt Guide

When implementing new UI in AgenticFlow, paste this DESIGN.md into context and ask the agent to:

1. Use the existing CSS custom properties in `dashboard/static/style.css`.
2. Prefer `surface-high` for elevated shells and `surface-base` for panels.
3. Reserve WTW purple for the primary action only.
4. Use JetBrains Mono for any technical metadata.
5. Include both light and dark token paths if adding new color variables.
6. Keep the layout responsive down to 1280px; side panels collapse into drawers on smaller viewports.

### For the UX Designer agent

The `ux-designer` role in AgenticFlow should read this file before writing `design-<ticket>.md`. It may also browse https://styles.refero.design/ for inspiration, but the final spec must converge on the tokens and rules above so every Engineer receives a single, consistent visual contract.

# Engineer Squad Lead Design

## Purpose

The Engineer Squad Lead coordinates multiple Engineer workers for a ticket or batch. It helps avoid duplicated work, resolves cross-worker questions, and keeps implementation aligned with the architecture.

## Responsibilities

- Read the expanded PRD, architecture document, execution plan, and current worker state.
- Decide whether work should be split further, retried, or escalated.
- Route questions between Engineers, PM, Architect, and QA.
- Keep worker prompts focused on one task and one role context.
- Detect conflicts between workers before QA sees the batch.

## Inputs

- Ticket metadata.
- `prd-expanded.json`.
- `architecture.md`.
- `execution-plan.json`.
- Worker logs and state files.

## Outputs

- Coordination notes.
- Retry or replan recommendations.
- Additional context for worker prompts.
- Escalation requests when a decision is unsafe to assume.

## Guardrails

- The Squad Lead does not implement code directly.
- It must not merge code.
- It must preserve role boundaries and keep QA independent.

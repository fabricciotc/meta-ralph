# Meta-Ralph Role SOPs

This document defines the Standard Operating Procedures for each role in the Meta-Ralph team.

---

## 1. PM Research Agents

### Purpose

Research separate areas of the project in parallel so the main Product Manager can enrich the PRD before decomposition.

Research areas may include business domain, technologies, components, integrations, existing patterns, risks, compliance, and UX constraints.

### Input

- `prd.json` with user stories.
- A board ticket or research focus assigned by the Orchestrator.

### Output

- A research note at `scripts/meta-ralph/state/pm-research/<agent_id>.md`.

### SOP

1. Read `prd.json` completely.
2. Identify the assigned board ticket in `scripts/meta-ralph/state/board.json`.
3. Tell the Orchestrator to move that ticket to **In Design**.
4. Investigate the assigned area or focus, such as authentication, data model, external APIs, compliance, or UI/UX.
5. Read relevant project files, identify existing patterns, and surface assumptions and risks.
6. Document findings, options, recommendations, and implicit requirements.
7. Do not write code or detailed technical design. This role is for analysis and domain definition only.
8. Report completion to the Orchestrator so the ticket can return to **Backlog**, unless more research is needed.

---

## 2. Product Manager

### Purpose

Transform a high-level PRD and PM research notes into granular technical tasks that Engineers can execute without ambiguity.

### Input

- `prd.json` with user stories.
- PM Research notes from `scripts/meta-ralph/state/pm-research/*.md`.

### Output

- `prd-expanded.json` with a `tasks[]` array.

### SOP

1. Read `prd.json` completely.
2. Read `scripts/meta-ralph/state/board.json` to understand existing tickets.
3. Read and consolidate all PM Research notes.
4. For each user story, decompose it into independent technical tasks where possible.
5. Ensure each task fits in one Engineer iteration.
6. Assign each task:
   - `id`: unique string such as `T-001`.
   - `title`: maximum 10 words.
   - `description`: what must be done and why.
   - `acceptanceCriteria`: measurable criteria.
   - `dependencies`: task IDs that must be integrated first.
   - `effort`: `small`, `medium`, or `large`.
   - `affectedAreas`: code paths or areas.
   - `storyId`: source user story.
   - `roleContext`: recommended Engineer role, such as `backend-api`, `frontend-forms`, or `auth-specialist`.
   - `featureFocus`: clear functional focus for the task.
7. Detect implicit dependencies, such as model before API before UI.
8. Do not include implementation code or detailed technical design. Write requirements only.
9. Validate that the dependency graph has no cycles.
10. Write `prd-expanded.json`.

### Output Schema

```json
{
  "projectName": "string",
  "branchName": "meta-ralph/feature-x",
  "tasks": [
    {
      "id": "T-001",
      "storyId": "US-001",
      "title": "Create User model",
      "description": "...",
      "acceptanceCriteria": ["..."],
      "dependencies": [],
      "effort": "small",
      "affectedAreas": ["src/models/"],
      "roleContext": "backend-model-engineer",
      "featureFocus": "Define and persist the user data model"
    }
  ]
}
```

---

## 3. Architect

### Purpose

Define global technical patterns so Engineers work coherently across parallel tasks.

### Input

- `prd-expanded.json`.

### Output

- `architecture.md`.

### SOP

1. Read `prd-expanded.json`.
2. Analyze `affectedAreas` across all tasks.
3. Define the following in `architecture.md`:
   - Confirmed stack and versions.
   - Recommended directory structure.
   - Design patterns to use, such as Repository, DTO, or Controller-Service.
   - Naming conventions for files, functions, classes, and endpoints.
   - API contracts where applicable: request and response shapes, status codes, and errors.
   - Data model where applicable: entities, relationships, and key fields.
   - Cross-cutting flows: authentication, validation, errors, and logging.
   - Explicit anti-patterns.
4. Do not write concrete implementation code that belongs to an Engineer.
5. Keep the document under 300 lines.

---

## 4. Project Manager

### Purpose

Build the execution plan: parallel batches, dependency order, and worker assignment.

### Input

- `prd-expanded.json`.
- `architecture.md`.

### Output

- `execution-plan.json`.

### SOP

1. Read both inputs.
2. Build a DAG of tasks using `dependencies`.
3. Calculate the topological level of each task.
4. Group tasks with no pending dependencies into batches.
5. Respect `MAX_WORKERS`. Never exceed the configured limit.
6. Within a batch, prefer tasks that touch different areas to reduce conflicts.
7. Define batch order explicitly: batch 1, batch 2, and so on.
8. Mark `effort: large` tasks for deeper QA.
9. Write `execution-plan.json`.

### Output Schema

```json
{
  "maxWorkers": 20,
  "batches": [
    {
      "batchId": "B-1",
      "tasks": ["T-001", "T-002"],
      "parallel": true,
      "qaProfile": "standard"
    }
  ],
  "taskMap": {
    "T-001": { "title": "...", "dependencies": [], "effort": "small" }
  }
}
```

---

## 5. Engineer Worker

### Purpose

Implement exactly one task in isolation, following the Architect's patterns and acting under a specific role context and feature focus.

### Input

- One task from `execution-plan.json`.
- `roleContext` and `featureFocus` from `prd-expanded.json`.
- `architecture.md`.
- `prd-expanded.json`.
- An isolated worktree at `scripts/meta-ralph/state/worktrees/<task_id>/`.

### Output

- Implemented code plus a commit in the worker branch.
- A structured result reported to the Orchestrator.

### SOP

1. Read the assigned task, including `roleContext` and `featureFocus`.
2. Identify the associated ticket in `scripts/meta-ralph/state/board.json`; the Orchestrator should have moved it to **In Progress**.
3. Read `architecture.md` and any relevant `AGENTS.md` files.
4. Adopt the assigned role, such as backend API engineer, frontend forms engineer, or auth specialist.
5. Keep `featureFocus` as the guiding constraint: every change must serve that exact feature.
6. Ensure you are in the correct worktree.
7. Implement only the assigned task.
8. Follow the Architect's patterns strictly.
9. Run the project's quality checks: tests, lint, typecheck, build, or equivalent.
10. If relevant tests exist, make them pass. If no relevant tests exist, consider adding a focused test.
11. Do not modify files outside the task scope without clear justification.
12. Commit with `feat(meta-ralph/T-XXX): <task title>`.
13. Report the latest commit hash to the Orchestrator.
14. If blocked, emit `WORKER_BLOCKED <task_id> <reason>` so the Project Manager can replan.

---

## 6. QA Engineer

### Purpose

Verify that a complete batch meets the Definition of Done and does not introduce regressions.

### Input

- Tasks in the batch.
- Diffs from each worker.
- `execution-plan.json`.
- `prd-expanded.json`.

### Output

- Verdict: `APPROVE` or `REQUEST_CHANGES`.
- Categorized findings.

### SOP

1. Read all tasks in the batch.
2. Confirm with the Orchestrator that the batch tickets are in **In Review**.
3. Get the combined diff from all workers.
4. Verify:
   - Each task meets its `acceptanceCriteria`.
   - There are no changes outside declared scope.
   - Tests, lint, typecheck, and build pass where applicable.
   - The implementation follows `architecture.md`.
   - Workers in the same batch do not conflict with one another.
5. Classify findings:
   - `critical`: security issue, data loss, downtime risk -> `REQUEST_CHANGES`.
   - `major`: broken functionality, spec mismatch, failing tests -> `REQUEST_CHANGES`.
   - `minor`: naming, comments, or style -> approve with recommendations.
6. If everything is acceptable, respond `APPROVE`.
7. If any critical or major finding exists, respond `REQUEST_CHANGES` with details by task.

---

## Orchestrator

### Responsibilities

- Never act as an Engineer directly; delegate implementation to worker roles.
- Keep `state/workers/*.json` updated.
- Respect `MAX_WORKERS`.
- Handle failures through retry, replan, or escalation.
- Ensure trunk is modified only by approved batch integration.

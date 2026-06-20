# Dynamic Subagent Swarm Design

**Date:** 2026-06-19  
**Status:** Approved  
**Scope:** `dashboard/core/orchestrator.py`, new `dashboard/core/dynamic_swarm.py`, role registry, tests.

## 1. Problem

The current MetaRalph pipeline runs a fixed set of roles (PM Analysis, UX Design, Architecture, Design Review, Planning, Engineer Squad, QA). Complex requirements often benefit from domain specialists (security, performance, integrations, accessibility, i18n, data architecture, DevOps) that are not part of the default flow. We want the Orchestrator to detect when extra specialists are useful, spawn them in parallel, collect their findings, and synthesize them into the shared context so downstream roles can act on them.

## 2. Goals

- Add a **dynamic swarm phase** between Planning and Execution.
- Let an AI-powered **detector** decide which specialists (if any) are relevant for a given ticket.
- Run each selected pre-defined specialist role in parallel with a configurable worker limit.
- Persist each specialist's findings to `meta/dynamic-swarm/{ticket}-{agent}.md`.
- Synthesize all findings into `meta/dynamic-swarm/swarm-report-{ticket}.md` and publish the summary into `Context.shared`.
- Integrate seamlessly with existing Orchestrator state machine and UI phases.

## 3. Non-Goals

- Replace the existing fixed pipeline.
- Modify the Tauri shell or frontend beyond exposing the new phase status.
- Implement real-time collaborative editing of specialist outputs.

## 4. Architecture

```text
+-------------+     +-------------------+     +----------------------+
|  Planning   | --> | Dynamic Swarm     | --> |  Engineer Squad      |
|  (existing) |     | (new, optional)   |     |  (existing)          |
+-------------+     +-------------------+     +----------------------+
                    | 1. Detector       |
                    | 2. Role Registry  |
                    | 3. Executor       |
                    | 4. Synthesizer    |
                    +-------------------+
```

### 4.1 Components

1. **`DynamicSwarmDetector`**
   - Input: ticket title/description, PRD content, architecture content, plan content.
   - Output: list of pre-defined specialist role IDs selected from `role_skills_registry.yaml` (`["security-specialist", "performance-specialist", ...]`).
   - Uses the configured AI backend via `invoke_ai` to classify the requirement against the registry.
   - Includes keyword heuristics to force specialists when certain terms appear (e.g., "OAuth", "encryption", "performance", "scale", "accessibility", "i18n", "GDPR").

2. **Pre-defined specialist roles in `role_skills_registry.yaml`**
   - `security_specialist`: skill `code-review` + focus on security, auth, secrets, injection, OWASP.
   - `performance_specialist`: skill `systematic-debugging` + focus on latency, throughput, caching, profiling.
   - `integrations_specialist`: skill `tech-research` + focus on third-party APIs, webhooks, data exchange.
   - `accessibility_specialist`: skill `ui` + focus on a11y, WCAG, keyboard navigation.
   - `data_architect`: skill `code-review` + focus on data modeling, migrations, persistence.
   - Cada rol tiene `prompt_prefix` específico de su especialidad y se ejecuta como subagente del swarm.

3. **`DynamicSwarmExecutor`**
   - Spawns each selected specialist using its registered role class.
   - Runs them in parallel using `asyncio.gather` with `semaphore` bounded by `max_dynamic_swarm_workers`.
   - Each specialist writes findings to `meta/dynamic-swarm/{ticket}-{agent_id}.md`.
   - Notifies agent status via the existing `update_agent` callback.

4. **`DynamicSwarmSynthesizer`**
   - Reads all specialist files.
   - Produces `meta/dynamic-swarm/swarm-report-{ticket}.md` with an executive summary, per-specialist highlights, and actionable recommendations.
   - Updates `Context.shared["swarm_findings"]` with the report path and a short summary.

5. **Orchestrator integration**
   - New state phase `dynamic_swarm` inserted after `planning` and before `execution`.
   - Skipped if the detector returns no specialists or if `enable_dynamic_swarm` is false.
   - UI phase label: "Swarm Review".

## 5. Data Flow

1. Orchestrator finishes `planning`.
2. If enabled, calls `DynamicSwarmDetector.detect(...)`.
3. If specialists found, transitions state to `dynamic_swarm`.
4. `DynamicSwarmExecutor.run(...)` runs specialists in parallel.
5. `DynamicSwarmSynthesizer.synthesize(...)` generates the report.
6. Orchestrator stores report path in `Context.shared` and transitions to `execution`.
7. Engineer Squad and QA prompts include the swarm report path/content when available.

## 6. Configuration

- `enable_dynamic_swarm`: bool, default `true`.
- `max_dynamic_swarm_workers`: int, default `6`.
- `dynamic_swarm_timeout_seconds`: int, default `600`.

Configuration lives in `orchestrator.py` defaults and can be overridden via the ticket's `config` dict.

## 7. Error Handling

- If the detector fails, log a warning and skip the phase (fallback: no specialists).
- If a single specialist fails, continue with the remaining specialists and note the failure in the report.
- If the synthesizer fails, still keep individual specialist files and log the error.

## 8. Testing

- Unit test detector with mocked AI and keyword heuristics.
- Unit test executor with mocked specialists.
- Unit test synthesizer file aggregation.
- Orchestrator integration test: verify `dynamic_swarm` phase runs and populates `Context.shared`.

## 9. Open Questions / Decisions

- The detector uses both AI reasoning and keyword heuristics to avoid missing obvious domain needs.
- Specialists are selected from pre-defined roles in `role_skills_registry.yaml`; the executor instantiates the registered role class for each selection.
- Parallelism is bounded by a semaphore rather than unbounded `asyncio.gather` to protect the AI backend.

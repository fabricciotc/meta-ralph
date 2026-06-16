# MetaGPT Improvements Plan

## Goal

Improve Meta-Ralph's role separation, planning quality, execution safety, and dashboard observability before publication.

## Work Items

- Clarify the role SOPs for PM Research, Product Manager, Architect, Project Manager, Engineer, and QA.
- Ensure Engineer workers always receive a specific role context and feature focus.
- Keep the Orchestrator out of implementation work.
- Add or improve batch-level QA gates.
- Keep dashboard board state synchronized with runtime state.
- Make backend selection assistant-neutral instead of tied to one CLI.

## Acceptance Criteria

- Public documentation is in native English.
- CLI mode can run with configurable AI backends.
- Native skill mode includes fallbacks for hosts without background subagents.
- Dashboard and worker state remain understandable during long runs.

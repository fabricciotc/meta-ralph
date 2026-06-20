# Dynamic Subagent Swarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `dynamic_swarm` phase to the MetaRalph pipeline that detects relevant pre-defined specialist roles, runs them in parallel, and synthesizes their findings into a shared report.

**Architecture:** A new `dashboard/core/dynamic_swarm.py` module provides a detector (keyword + AI), an executor (parallel `PMResearchRole` instances), and a synthesizer. The orchestrator calls them between Planning and Execution. Specialist roles are declared in `role_skills_registry.yaml` so the existing skill-injection system can load their prompts.

**Tech Stack:** Python 3.11+, Flask dashboard, existing `core/environment.py`, `core/roles/pm_research_role.py`, `core/skills_registry.py`, `pytest`.

---

## File map

| File | Responsibility |
|------|----------------|
| `dashboard/core/role_skills_registry.yaml` | Declare pre-defined specialist roles (`security_specialist`, `performance_specialist`, `integrations_specialist`, `accessibility_specialist`, `data_architect`). |
| `dashboard/core/dynamic_swarm.py` | `DynamicSwarmDetector`, `DynamicSwarmExecutor`, `DynamicSwarmSynthesizer`, plus prompt builders and the registry of available specialists. |
| `dashboard/core/orchestrator.py` | Insert `dynamic_swarm` phase between Planning and Execution; update `_infer_role_from_phase` to resolve registered specialist role IDs. |
| `dashboard/core/skills_registry.py` | Add `has_role(role_id)` helper so the orchestrator can safely resolve unknown phase names against the registry. |
| `dashboard/tests/test_dynamic_swarm.py` | Unit tests for detector, executor, synthesizer, and orchestrator phase hook. |

---

### Task 1: Register specialist roles

**Files:**
- Modify: `dashboard/core/role_skills_registry.yaml`

- [ ] **Step 1: Append five specialist roles to the registry**

Append the following entries at the end of `dashboard/core/role_skills_registry.yaml`:

```yaml
security_specialist:
  skills:
    - code-review
  prompt_prefix: |
    You are a Security Specialist. Focus on authentication, authorization, secrets management, injection attacks, OWASP Top 10, data privacy, and secure coding practices. Produce findings and actionable recommendations. Do NOT write concrete implementation code.

performance_specialist:
  skills:
    - systematic-debugging
  prompt_prefix: |
    You are a Performance Specialist. Focus on latency, throughput, caching, memory usage, profiling, and scalability. Identify bottlenecks and recommend concrete optimizations. Do NOT write concrete implementation code.

integrations_specialist:
  skills:
    - tech-research
  prompt_prefix: |
    You are an Integrations Specialist. Focus on third-party APIs, webhooks, data exchange formats, authentication flows for external services, and error handling. Produce integration recommendations. Do NOT write concrete implementation code.

accessibility_specialist:
  skills:
    - ui
  prompt_prefix: |
    You are an Accessibility Specialist. Focus on WCAG compliance, keyboard navigation, screen reader support, color contrast, and semantic HTML. Produce accessibility findings and recommendations. Do NOT write concrete implementation code.

data_architect:
  skills:
    - code-review
  prompt_prefix: |
    You are a Data Architect. Focus on data modeling, schema design, migrations, persistence strategy, query performance, and data integrity. Produce data architecture recommendations. Do NOT write concrete implementation code.
```

- [ ] **Step 2: Validate YAML syntax**

Run:

```bash
cd dashboard && python -c "import yaml; yaml.safe_load(open('core/role_skills_registry.yaml'))" && echo "OK"
```

Expected: prints `OK` with no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/core/role_skills_registry.yaml
git commit -m "feat(swarm): register pre-defined specialist roles"
```

---

### Task 2: Add `has_role` helper to SkillsRegistry

**Files:**
- Modify: `dashboard/core/skills_registry.py`

- [ ] **Step 1: Add the helper method**

Insert the following method into `SkillsRegistry` after `get_prompt_prefix`:

```python
    def has_role(self, role: str) -> bool:
        """Return True if the registry knows this role ID."""
        return role in self._data
```

- [ ] **Step 2: Write a failing test for the helper**

Create `dashboard/tests/test_dynamic_swarm.py` with this initial content:

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.modules.setdefault("yaml", MagicMock())
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.skills_registry import SkillsRegistry


class TestSkillsRegistryHasRole(unittest.TestCase):
    def test_has_role_returns_true_for_known_role(self):
        registry = SkillsRegistry.__new__(SkillsRegistry)
        registry._data = {"security_specialist": {"skills": ["code-review"]}}
        self.assertTrue(registry.has_role("security_specialist"))

    def test_has_role_returns_false_for_unknown_role(self):
        registry = SkillsRegistry.__new__(SkillsRegistry)
        registry._data = {"security_specialist": {"skills": ["code-review"]}}
        self.assertFalse(registry.has_role("unknown_role"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd dashboard && python -m pytest tests/test_dynamic_swarm.py::TestSkillsRegistryHasRole -v
```

Expected: two `AttributeError` failures because `has_role` does not exist yet.

- [ ] **Step 4: Run the test to verify it passes**

After adding the helper in Step 1:

```bash
cd dashboard && python -m pytest tests/test_dynamic_swarm.py::TestSkillsRegistryHasRole -v
```

Expected: two passing tests.

- [ ] **Step 5: Commit**

```bash
git add dashboard/core/skills_registry.py dashboard/tests/test_dynamic_swarm.py
git commit -m "feat(swarm): add SkillsRegistry.has_role helper"
```

---

### Task 3: Create `dashboard/core/dynamic_swarm.py`

**Files:**
- Create: `dashboard/core/dynamic_swarm.py`

- [ ] **Step 1: Write the module**

Create `dashboard/core/dynamic_swarm.py` with the following content:

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.ai_execution import invoke_ai
from core.environment import Environment
from core.models import Message
from core.roles.pm_research_role import PMResearchRole


DEFAULT_SPECIALIST_ROLES: Dict[str, str] = {
    "security_specialist": "Security, authentication, secrets, injection, OWASP, data privacy.",
    "performance_specialist": "Performance, latency, throughput, caching, profiling, scalability.",
    "integrations_specialist": "Third-party APIs, webhooks, data exchange, external auth flows.",
    "accessibility_specialist": "Accessibility, WCAG, keyboard navigation, screen readers.",
    "data_architect": "Data modeling, schema design, migrations, persistence, data integrity.",
}

KEYWORD_SPECIALIST_MAP: Dict[str, List[str]] = {
    "security_specialist": [
        "security", "auth", "oauth", "sso", "secret", "credential", "password",
        "jwt", "encrypt", "owasp", "injection", "xss", "csrf", "gdpr", "privacy",
    ],
    "performance_specialist": [
        "performance", "latency", "throughput", "cache", "scaling", "scale",
        "optimize", "profil", "slow", "bottleneck", "memory leak",
    ],
    "integrations_specialist": [
        "integration", "api", "webhook", "third-party", "third party",
        "external service", "sync", "connector",
    ],
    "accessibility_specialist": [
        "accessibility", "a11y", "wcag", "screen reader", "keyboard",
        "contrast", "aria",
    ],
    "data_architect": [
        "database", "schema", "migration", "persist", "data model", "sql",
        "nosql", "entity", "relation",
    ],
}


def build_dynamic_specialist_prompt(
    role_id: str,
    focus: str,
    title: str,
    description: str,
    follow_up: Optional[str],
    context: Any,
) -> str:
    """Build a research prompt for a dynamic specialist subagent."""
    artifacts: List[str] = []
    if getattr(context, "prd_path", None) and context.prd_path.exists():
        artifacts.append(f"PRD:\n{context.prd_path.read_text(encoding='utf-8')[:2000]}")
    if getattr(context, "architecture_path", None) and context.architecture_path.exists():
        artifacts.append(f"ARCHITECTURE:\n{context.architecture_path.read_text(encoding='utf-8')[:2000]}")
    if getattr(context, "tasks_path", None) and context.tasks_path.exists():
        try:
            artifacts.append(f"TASKS:\n{context.tasks_path.read_text(encoding='utf-8')[:2000]}")
        except Exception:
            pass
    if getattr(context, "design_path", None) and context.design_path.exists():
        artifacts.append(f"DESIGN:\n{context.design_path.read_text(encoding='utf-8')[:2000]}")

    artifacts_text = "\n\n---\n\n".join(artifacts) or "No artifacts available."

    follow_up_section = ""
    if follow_up:
        follow_up_section = (
            "\n\nFOLLOW-UP QUESTION:\n"
            f"{follow_up}\n\n"
            "Answer directly while keeping the same output format."
        )

    return (
        f"You are the {role_id.replace('_', ' ').title()} for a MetaGPT-style multi-agent software factory. "
        f"Your exclusive focus is: {focus}. "
        "Analyze the provided artifacts ONLY from your assigned angle. "
        "Do NOT implement code; only research, analyze, and document findings. "
        "Be concise but complete; prioritize quality over length.\n\n"
        "Your output must be markdown with these sections:\n"
        "1. Key findings (maximum 10 bullets).\n"
        "2. Risks or concerns relevant to your area.\n"
        "3. Concrete recommendations for the Engineer Squad.\n"
        "4. Open questions (if any).\n\n"
        f"TICKET:\nTITLE: {title}\nDESCRIPTION: {description}\n\n"
        f"ARTIFACTS:\n{artifacts_text}"
        + follow_up_section
        + "\n\nRespond in English."
    )


class DynamicSwarmDetector:
    """Detects which pre-defined specialist roles are relevant for a ticket."""

    def __init__(
        self,
        run_ai: Optional[Callable] = None,
        skills_registry: Optional[Any] = None,
        timeout_seconds: int = 120,
    ):
        self.run_ai = run_ai
        self.skills_registry = skills_registry
        self.timeout_seconds = timeout_seconds

    def detect(self, ticket: Dict[str, Any], context_text: str) -> List[str]:
        """Return a list of relevant specialist role IDs."""
        keyword_roles = self._keyword_detect(context_text)
        ai_roles = self._ai_detect(ticket, context_text)
        seen: set = set()
        result: List[str] = []
        for role in keyword_roles + ai_roles:
            if role in DEFAULT_SPECIALIST_ROLES and role not in seen:
                result.append(role)
                seen.add(role)
        return result

    def _keyword_detect(self, text: str) -> List[str]:
        text_lower = text.lower()
        found: List[str] = []
        for role, keywords in KEYWORD_SPECIALIST_MAP.items():
            if any(kw in text_lower for kw in keywords):
                found.append(role)
        return found

    def _ai_detect(self, ticket: Dict[str, Any], context_text: str) -> List[str]:
        if not self.run_ai:
            return []
        prompt = self._build_detect_prompt(ticket, context_text)
        try:
            raw = invoke_ai(
                self.run_ai,
                prompt,
                "dynamic_swarm_detect",
                self.timeout_seconds,
                agent_id="dynamic-swarm-detector",
            )
            return self._parse_detect_response(raw or "")
        except Exception:
            return []

    def _build_detect_prompt(self, ticket: Dict[str, Any], context_text: str) -> str:
        role_list = "\n".join(
            f"- {rid}: {focus}" for rid, focus in DEFAULT_SPECIALIST_ROLES.items()
        )
        return (
            "You are a Dynamic Swarm Detector for a multi-agent software factory. "
            "Given a ticket and its generated artifacts, decide which pre-defined specialist roles "
            "should be added to the pipeline to improve quality. Only return roles that are truly relevant.\n\n"
            f"AVAILABLE ROLES:\n{role_list}\n\n"
            f"TICKET TITLE: {ticket.get('title', '')}\n"
            f"TICKET DESCRIPTION: {ticket.get('description', '')}\n\n"
            f"ARTIFACTS CONTEXT:\n{context_text[:4000]}\n\n"
            "Respond EXACTLY with JSON in this shape:\n"
            '{"specialists": ["security_specialist", "performance_specialist"]}\n'
            'If no specialists are needed, return {"specialists": []}.'
        )

    def _parse_detect_response(self, raw: str) -> List[str]:
        text = raw.strip()
        if "```" in text:
            blocks = text.split("```")
            for block in blocks:
                candidate = block.strip()
                if candidate.startswith("{"):
                    text = candidate
                    break
        try:
            data = json.loads(text)
            return [r for r in data.get("specialists", []) if r in DEFAULT_SPECIALIST_ROLES]
        except Exception:
            return []


class DynamicSwarmExecutor:
    """Runs selected specialist roles in parallel and writes their findings to disk."""

    def __init__(
        self,
        run_ai: Optional[Callable] = None,
        update_agent: Optional[Callable] = None,
        max_workers: int = 6,
        timeout_seconds: int = 600,
    ):
        self.run_ai = run_ai
        self.update_agent = update_agent
        self.max_workers = max(1, max_workers)
        self.timeout_seconds = timeout_seconds

    async def run(
        self,
        ticket: Dict[str, Any],
        role_ids: List[str],
        context: Any,
        output_dir: Path,
    ) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _run_one(role_id: str) -> Optional[Path]:
            async with semaphore:
                name = role_id.replace("_", " ").title()
                focus = DEFAULT_SPECIALIST_ROLES.get(role_id, "specialist analysis")
                role = PMResearchRole(
                    role_id=role_id,
                    sub_name=name,
                    focus=focus,
                    run_ai=self.run_ai,
                )
                env = Environment()
                env.add_role(role)

                def build_prompt(
                    sub_id: str,
                    focus: str,
                    title: str,
                    description: str,
                    follow_up: Optional[str],
                ) -> str:
                    return build_dynamic_specialist_prompt(
                        role_id, focus, title, description, follow_up, context
                    )

                def _update(agent_id: str, **kwargs: Any) -> None:
                    if self.update_agent:
                        self.update_agent(agent_id, **kwargs)

                env.publish_message(Message(
                    content=f"Start {role_id}",
                    sent_from="orchestrator",
                    cause_by="research_request",
                    send_to={role_id},
                    metadata={
                        "ticket_title": ticket.get("title", ""),
                        "ticket_description": ticket.get("description", ""),
                        "ticket_id": ticket.get("id", ""),
                        "output_dir": output_dir,
                        "build_prompt": build_prompt,
                        "update_agent": _update,
                        "phase_name": role_id,
                        "timeout_seconds": self.timeout_seconds,
                    },
                ))

                for _ in range(5):
                    active = await env.run_round(context=context)
                    if not active and env.is_idle():
                        break

                for msg in reversed(env.history()):
                    if msg.metadata.get("sub_id") == role_id and msg.metadata.get("file"):
                        return Path(msg.metadata["file"])
                return None

        results = await asyncio.gather(
            *[_run_one(r) for r in role_ids],
            return_exceptions=True,
        )
        files: Dict[str, Path] = {}
        for role_id, result in zip(role_ids, results):
            if isinstance(result, Path):
                files[role_id] = result
            elif isinstance(result, Exception):
                if hasattr(context, "log"):
                    context.log(f"Specialist {role_id} failed: {result}", "warning")
        return files


class DynamicSwarmSynthesizer:
    """Combines specialist findings into a single markdown report."""

    def __init__(
        self,
        run_ai: Optional[Callable] = None,
        timeout_seconds: int = 300,
    ):
        self.run_ai = run_ai
        self.timeout_seconds = timeout_seconds

    async def synthesize(
        self,
        ticket: Dict[str, Any],
        files: Dict[str, Path],
        output_path: Path,
    ) -> str:
        if not files:
            return ""

        findings: List[str] = []
        for role_id, path in files.items():
            try:
                text = path.read_text(encoding="utf-8")
                findings.append(f"--- {role_id} ---\n\n{text[:2000]}")
            except Exception as exc:
                findings.append(f"--- {role_id} ---\n\nError reading file: {exc}")

        prompt = (
            "You are a Swarm Synthesizer for a multi-agent software factory. "
            "Consolidate the findings of the specialist agents into an executive report for the Engineer Squad and QA.\n\n"
            f"TICKET:\nTITLE: {ticket.get('title', '')}\nDESCRIPTION: {ticket.get('description', '')}\n\n"
            "SPECIALIST FINDINGS:\n" + "\n\n".join(findings) + "\n\n"
            "Generate a concise markdown report with these sections:\n"
            "1. Executive summary\n"
            "2. Per-specialist highlights\n"
            "3. Actionable recommendations for implementation\n"
            "4. Open questions or risks to monitor"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            output = await invoke_ai(
                self.run_ai,
                prompt,
                "dynamic_swarm_synthesize",
                self.timeout_seconds,
                agent_id="dynamic-swarm-synthesizer",
            )
        except Exception:
            output = None

        if not output:
            output = "# Dynamic Swarm Report\n\n" + "\n\n".join(findings)

        output_path.write_text(output, encoding="utf-8")
        return output
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd dashboard && python -c "from core.dynamic_swarm import DynamicSwarmDetector, DynamicSwarmExecutor, DynamicSwarmSynthesizer; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add dashboard/core/dynamic_swarm.py
git commit -m "feat(swarm): add dynamic swarm detector, executor, and synthesizer"
```

---

### Task 4: Integrate dynamic swarm into the orchestrator

**Files:**
- Modify: `dashboard/core/orchestrator.py`

- [ ] **Step 1: Import the swarm module**

Add this import near the top of `dashboard/core/orchestrator.py` (after the existing role imports):

```python
from core.dynamic_swarm import (
    DynamicSwarmDetector,
    DynamicSwarmExecutor,
    DynamicSwarmSynthesizer,
)
```

- [ ] **Step 2: Update `_infer_role_from_phase` to resolve registered specialists**

Replace the existing `_infer_role_from_phase` method with:

```python
    def _infer_role_from_phase(self, phase_name: str) -> str:
        mapping = {
            "pm_research": "pm_research",
            "pm_consolidate": "product_manager",
            "architect": "architect",
            "design_review": "architect",
            "planning": "project_manager",
            "engineer": "engineer",
            "qa_review": "qa",
            "qa_correction": "qa",
            "dynamic_swarm": "dynamic_swarm",
            "dynamic_swarm_detect": "dynamic_swarm",
            "dynamic_swarm_synthesize": "dynamic_swarm",
        }
        lowered = phase_name.lower()
        for key, role in mapping.items():
            if key in lowered:
                return role
        if self.skills_registry and self.skills_registry.has_role(phase_name):
            return phase_name
        return "engineer"
```

- [ ] **Step 3: Add helper methods for swarm paths and context**

Insert these helper methods after `_branch(self)`:

```python
    def _swarm_output_dir(self) -> Path:
        return self._meta_dir() / "dynamic-swarm"

    def _swarm_report_path(self) -> Path:
        return self._meta_dir() / "state" / f"swarm-report-{self.ticket_id}.md"

    def _build_swarm_context_text(self) -> str:
        parts: List[str] = []
        prd_path = self._prd_path()
        if prd_path.exists():
            parts.append(f"PRD:\n{prd_path.read_text(encoding='utf-8')}")
        arch_path = self._architecture_path()
        if arch_path.exists():
            parts.append(f"ARCHITECTURE:\n{arch_path.read_text(encoding='utf-8')}")
        design_path = self._design_path()
        if design_path.exists():
            parts.append(f"DESIGN:\n{design_path.read_text(encoding='utf-8')}")
        tasks_path = self._tasks_path()
        if tasks_path.exists():
            parts.append(f"TASKS:\n{tasks_path.read_text(encoding='utf-8')}")
        return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Insert the new phase into the main run loop**

Replace this block in `run()`:

```python
            if state.get("phase") == "planning":
                self._run_phase_3_planning()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "execution"
                self._save_resume_state(state)
```

with:

```python
            if state.get("phase") == "planning":
                self._run_phase_3_planning()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "dynamic_swarm"
                self._save_resume_state(state)

            if state.get("phase") == "dynamic_swarm":
                self._run_phase_3_5_dynamic_swarm()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "execution"
                self._save_resume_state(state)
```

- [ ] **Step 5: Implement `_run_phase_3_5_dynamic_swarm`**

Insert the following method after `_run_phase_3_planning`:

```python
    def _run_phase_3_5_dynamic_swarm(self) -> None:
        config = self.ticket.get("config", {})
        if not config.get("enable_dynamic_swarm", True):
            self.log("Dynamic swarm disabled by config; skipping.")
            return

        self.log("Phase 3.5/5: Dynamic Swarm: selecting specialist subagents.")
        self._set_phase("dynamic-swarm", "in-design", 67)
        self._ensure_agent("dynamic-swarm", "Dynamic Swarm", "lead", "orchestrator", "running", 67)

        context_text = self._build_swarm_context_text()
        detector = DynamicSwarmDetector(
            run_ai=self._run_ai,
            skills_registry=self.skills_registry,
        )
        role_ids = detector.detect(self.ticket, context_text)

        if not role_ids:
            self.log("No dynamic specialists detected; skipping swarm phase.")
            self._update_agent("dynamic-swarm", status="done", progress=100, log="No specialists needed.")
            self._set_phase("dynamic-swarm", "in-progress", 70)
            return

        for role_id in role_ids:
            self._ensure_agent(role_id, role_id.replace("_", " ").title(), "sub", "dynamic-swarm", "queued", 0)

        self.log(f"Dynamic swarm detected specialists: {', '.join(role_ids)}")
        output_dir = self._swarm_output_dir()
        executor = DynamicSwarmExecutor(
            run_ai=self._run_ai,
            update_agent=self._update_agent,
            max_workers=config.get("max_dynamic_swarm_workers", 6),
            timeout_seconds=config.get("dynamic_swarm_timeout_seconds", 600),
        )
        files = asyncio.run(executor.run(self.ticket, role_ids, self.context, output_dir))

        synthesizer = DynamicSwarmSynthesizer(run_ai=self._run_ai)
        report_path = self._swarm_report_path()
        try:
            summary = asyncio.run(synthesizer.synthesize(self.ticket, files, report_path))
            self.context.set("swarm_findings", {
                "report_path": str(report_path),
                "specialists": role_ids,
                "files": {rid: str(p) for rid, p in files.items()},
                "summary": summary[:2000],
            })
            self.log(f"Dynamic swarm report saved at {report_path}")
        except Exception as exc:
            self.log(f"Swarm synthesis failed: {exc}", "warning")

        for role_id in role_ids:
            self._update_agent(role_id, status="done", progress=100, log=f"{role_id} completed.")
        self._update_agent("dynamic-swarm", status="done", progress=100, log=f"Swarm completed with {len(role_ids)} specialists.")
        self._set_phase("dynamic-swarm", "in-progress", 70)
```

- [ ] **Step 6: Run the existing orchestrator tests to catch regressions**

```bash
cd dashboard && python -m pytest tests/test_orchestrator_qa_status.py tests/test_orchestrator_qa_correction_loop.py tests/test_ticket_flow.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard/core/orchestrator.py
git commit -m "feat(swarm): integrate dynamic swarm phase into orchestrator"
```

---

### Task 5: Add unit tests for the dynamic swarm

**Files:**
- Modify: `dashboard/tests/test_dynamic_swarm.py`

- [ ] **Step 1: Append detector tests**

Add the following test classes to `dashboard/tests/test_dynamic_swarm.py` (after the existing `TestSkillsRegistryHasRole`):

```python
import tempfile

from core.dynamic_swarm import (
    DynamicSwarmDetector,
    DynamicSwarmExecutor,
    DynamicSwarmSynthesizer,
    KEYWORD_SPECIALIST_MAP,
)


class TestDynamicSwarmDetector(unittest.TestCase):
    def test_keyword_detect_finds_security_specialist(self):
        detector = DynamicSwarmDetector()
        roles = detector.detect(
            {"title": "Add OAuth", "description": "Implement OAuth2 login"},
            "We need secure authentication.",
        )
        self.assertIn("security_specialist", roles)

    def test_keyword_detect_finds_performance_specialist(self):
        detector = DynamicSwarmDetector()
        roles = detector.detect(
            {"title": "Optimize", "description": "Reduce latency"},
            "The endpoint is slow and needs caching.",
        )
        self.assertIn("performance_specialist", roles)

    def test_ai_detect_returns_valid_roles(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return '{"specialists": ["accessibility_specialist", "invalid_role"]}'

        detector = DynamicSwarmDetector(run_ai=mock_run_ai)
        roles = detector.detect(
            {"title": "UI", "description": "Build a form"},
            "No keyword hits here.",
        )
        self.assertIn("accessibility_specialist", roles)
        self.assertNotIn("invalid_role", roles)

    def test_detect_deduplicates_and_preserves_order(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return '{"specialists": ["security_specialist"]}'

        detector = DynamicSwarmDetector(run_ai=mock_run_ai)
        roles = detector.detect(
            {"title": "Auth", "description": "OAuth and JWT"},
            "security context",
        )
        self.assertEqual(roles.count("security_specialist"), 1)
        self.assertEqual(roles[0], "security_specialist")


class TestDynamicSwarmExecutor(unittest.TestCase):
    def test_executor_writes_specialist_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            class FakeContext:
                prd_path = output_dir / "prd.md"
                architecture_path = output_dir / "arch.md"
                tasks_path = output_dir / "tasks.json"
                design_path = output_dir / "design.md"

                def log(self, message, level="info"):
                    pass

            FakeContext.prd_path.write_text("# PRD\n\nBuild a login form.", encoding="utf-8")

            async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
                return f"# {agent_id} findings\n\nKey finding."

            executor = DynamicSwarmExecutor(run_ai=mock_run_ai, max_workers=2)
            files = asyncio.run(executor.run(
                ticket={"id": "TKT-1", "title": "Login", "description": "OAuth"},
                role_ids=["security_specialist"],
                context=FakeContext(),
                output_dir=output_dir,
            ))

            self.assertIn("security_specialist", files)
            self.assertTrue(files["security_specialist"].exists())
            content = files["security_specialist"].read_text(encoding="utf-8")
            self.assertIn("Key finding", content)


class TestDynamicSwarmSynthesizer(unittest.TestCase):
    def test_synthesizer_writes_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = {
                "security_specialist": Path(tmpdir) / "TKT-1-security_specialist.md",
            }
            files["security_specialist"].write_text("# Security findings", encoding="utf-8")
            output_path = Path(tmpdir) / "report.md"

            async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
                return "# Synthesized report"

            synthesizer = DynamicSwarmSynthesizer(run_ai=mock_run_ai)
            result = asyncio.run(synthesizer.synthesize(
                ticket={"id": "TKT-1", "title": "Login", "description": "OAuth"},
                files=files,
                output_path=output_path,
            ))

            self.assertIn("Synthesized report", result)
            self.assertTrue(output_path.exists())
```

- [ ] **Step 2: Append orchestrator phase hook test**

Add this test class at the end of `dashboard/tests/test_dynamic_swarm.py`:

```python
class TestOrchestratorSwarmPhase(unittest.TestCase):
    def test_build_swarm_context_text_includes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = Orchestrator(
                ticket={"id": "TKT-SWARM", "title": "Test", "description": "Desc"},
                callbacks={},
            )
            # Override meta dir so we can write artifact files.
            orchestrator._meta_dir = lambda: Path(tmpdir)

            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / f"prd-TKT-SWARM.md").write_text("# PRD", encoding="utf-8")
            (state_dir / f"architecture-TKT-SWARM.md").write_text("# Arch", encoding="utf-8")

            text = orchestrator._build_swarm_context_text()
            self.assertIn("# PRD", text)
            self.assertIn("# Arch", text)
```

- [ ] **Step 3: Run the new tests**

```bash
cd dashboard && python -m pytest tests/test_dynamic_swarm.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/tests/test_dynamic_swarm.py
git commit -m "test(swarm): add unit tests for dynamic swarm detector, executor, synthesizer"
```

---

### Task 6: Run full test suite and merge to master

**Files:**
- (no file changes)

- [ ] **Step 1: Run the full dashboard test suite**

```bash
cd dashboard && python -m pytest tests -q
```

Expected: all 186+ existing tests pass plus the new dynamic swarm tests.

- [ ] **Step 2: Fix any failures**

If tests fail, read the traceback, update the relevant file, and re-run the failing test(s) until green.

- [ ] **Step 3: Push to master**

```bash
git push origin master
```

Expected: push succeeds with the new commits.

---

## Spec coverage check

| Spec requirement | Plan task |
|------------------|-----------|
| Detector picks from pre-defined roles | Task 3 (`DynamicSwarmDetector`) |
| Keyword + AI detection | Task 3 (`detect`, `_keyword_detect`, `_ai_detect`) |
| Run specialists in parallel with worker limit | Task 3 (`DynamicSwarmExecutor`) |
| Write findings to `meta/dynamic-swarm/` | Task 3 (`DynamicSwarmExecutor.run`) |
| Synthesize report and update `Context.shared` | Task 3 (`DynamicSwarmSynthesizer`) + Task 4 |
| Orchestrator phase between Planning and Execution | Task 4 |
| Configurable `enable_dynamic_swarm`, `max_dynamic_swarm_workers`, timeout | Task 4 (`config` dict) |
| Skip phase when no specialists or disabled | Task 4 |
| Tests for detector/executor/synthesizer/orchestrator | Task 5 |

## Placeholder scan

No TBD/TODO/"implement later"/"appropriate" placeholders remain. Every step contains exact file paths, exact code, and exact commands.

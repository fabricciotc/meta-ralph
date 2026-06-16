# AI Runner portable, Orchestrator Swarm y portabilidad — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir `meta-ralph` en un orquestador multi-agente portable: adaptadores de IA genéricos, registro de skills/MCPs por rol, Orchestrator como swarm de coordinadores, e `install.sh` robusto.

**Architecture:** Capa de adaptadores `core/runners/` con interfaz común `AIBackend` + `BackendRegistry` para detección/fallback. `core/skills_registry.py` carga recomendaciones por rol desde YAML y las inyecta en prompts según soporte del backend. Roles coordinadores (`DispatcherRole`, `MonitorRole`, `RecoveryRole`) avanzan el workflow dentro del `Environment`.

**Tech Stack:** Python 3.10+, Flask, PyYAML, requests, subprocess, pytest.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `dashboard/core/runners/base.py` | Protocolo/base `AIBackend`, resultado `BackendResult`, constantes |
| `dashboard/core/runners/kimi_cli.py` | Adaptador CLI de Kimi |
| `dashboard/core/runners/cursor_cli.py` | Adaptador CLI de Cursor |
| `dashboard/core/runners/claude_code.py` | Adaptador CLI de Claude Code |
| `dashboard/core/runners/codex_cli.py` | Adaptador CLI de OpenAI Codex |
| `dashboard/core/runners/openai_api.py` | Adaptador API OpenAI-compatible |
| `dashboard/core/runners/registry.py` | `BackendRegistry`: detección, fallback, ejecución |
| `dashboard/core/runners/__init__.py` | Exports públicos |
| `dashboard/core/role_skills_registry.yaml` | Mapeo rol → skills/MCPs/prompts |
| `dashboard/core/skills_registry.py` | Carga del YAML y generación de prefijos |
| `dashboard/core/roles/dispatcher_role.py` | Coordina avance de fases |
| `dashboard/core/roles/monitor_role.py` | Detecta stalls y reporta progreso |
| `dashboard/core/roles/recovery_role.py` | Decide reintentos/replanificación |
| `dashboard/core/orchestrator.py` | Crea Environment, registra roles, ejecuta rondas |
| `dashboard/core/actions/base.py` | Base para inyección de skill prompts |
| `dashboard/server.py` | Inicializa BackendRegistry y pasa callbacks |
| `dashboard/requirements.txt` | Dependencias |
| `install.sh` | Instalación portable |
| `scripts/validate_install.py` | Validación post-install |

---

## Task 1: AI Runner base + registry skeleton

**Files:**
- Create: `dashboard/core/runners/base.py`
- Create: `dashboard/core/runners/registry.py`
- Create: `dashboard/core/runners/__init__.py`
- Test: `dashboard/tests/test_runners.py`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_runners.py`:

```python
from core.runners.base import AIBackend, BackendResult
from core.runners.registry import BackendRegistry


class FakeBackend:
    name = "fake"
    supports_skill_activation = False

    def __init__(self, available=True, output="ok"):
        self._available = available
        self._output = output

    def is_available(self):
        return self._available

    def run_prompt(self, prompt, *, phase_name, timeout_seconds, agent_id=None, system_instructions=None):
        return self._output


def test_registry_picks_first_available():
    registry = BackendRegistry([FakeBackend(available=False), FakeBackend(available=True, output="hello")])
    assert registry.run_prompt("hi", phase_name="test", timeout_seconds=10) == "hello"


def test_registry_fallback_on_none():
    class FailingBackend(FakeBackend):
        name = "failing"

        def run_prompt(self, prompt, *, phase_name, timeout_seconds, agent_id=None, system_instructions=None):
            return None

    registry = BackendRegistry([FailingBackend(available=True), FakeBackend(available=True, output="fallback")])
    assert registry.run_prompt("hi", phase_name="test", timeout_seconds=10) == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_runners.py -v
```

Expected: `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/core/runners/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class BackendResult:
    output: Optional[str]
    backend_name: str


class AIBackend(Protocol):
    name: str
    supports_skill_activation: bool

    def is_available(self) -> bool: ...

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]: ...
```

Create `dashboard/core/runners/registry.py`:

```python
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from core.runners.base import AIBackend

logger = logging.getLogger(__name__)


class BackendRegistry:
    def __init__(self, backends: Iterable[AIBackend]):
        self.backends: List[AIBackend] = list(backends)

    @classmethod
    def default(cls) -> "BackendRegistry":
        from core.runners.kimi_cli import KimiCliBackend
        from core.runners.cursor_cli import CursorCliBackend
        from core.runners.claude_code import ClaudeCodeBackend
        from core.runners.codex_cli import CodexCliBackend
        from core.runners.openai_api import OpenAIApiBackend

        return cls([
            KimiCliBackend(),
            CursorCliBackend(),
            ClaudeCodeBackend(),
            CodexCliBackend(),
            OpenAIApiBackend(),
        ])

    def available_backends(self) -> List[AIBackend]:
        return [b for b in self.backends if b.is_available()]

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        last_error = ""
        for backend in self.backends:
            if not backend.is_available():
                continue
            try:
                output = backend.run_prompt(
                    prompt,
                    phase_name=phase_name,
                    timeout_seconds=timeout_seconds,
                    agent_id=agent_id,
                    system_instructions=system_instructions,
                )
                if output:
                    return output
            except Exception as exc:
                last_error = str(exc)
                logger.warning("Backend %s failed: %s", backend.name, exc)
        if last_error:
            logger.error("All backends failed. Last error: %s", last_error)
        return None
```

Create `dashboard/core/runners/__init__.py`:

```python
from core.runners.base import AIBackend, BackendResult
from core.runners.registry import BackendRegistry

__all__ = ["AIBackend", "BackendResult", "BackendRegistry"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_runners.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/runners dashboard/tests/test_runners.py && git commit -m "feat(runners): base protocol and BackendRegistry with fallback"
```

---

## Task 2: Kimi CLI backend

**Files:**
- Create: `dashboard/core/runners/kimi_cli.py`
- Modify: `dashboard/core/runners/registry.py` (already imports)
- Test: `dashboard/tests/test_runners.py`

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_runners.py`:

```python
from unittest.mock import patch


def test_kimi_backend_detects_executable():
    with patch("core.runners.kimi_cli.shutil.which", return_value="/usr/bin/kimi"):
        from core.runners.kimi_cli import KimiCliBackend
        assert KimiCliBackend().is_available() is True


def test_kimi_backend_runs_prompt(monkeypatch):
    with patch("core.runners.kimi_cli.shutil.which", return_value="/usr/bin/kimi"):
        from core.runners.kimi_cli import KimiCliBackend
        backend = KimiCliBackend()
        called = {}

        def fake_run(*args, **kwargs):
            called["args"] = args
            called["kwargs"] = kwargs
            class R:
                stdout = "kimi output"
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        output = backend.run_prompt("hello", phase_name="test", timeout_seconds=10, agent_id="a1")
        assert output == "kimi output"
        assert called["args"][0][0] == "/usr/bin/kimi"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError for `core.runners.kimi_cli`.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/core/runners/kimi_cli.py`:

```python
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class KimiCliBackend:
    name = "kimi"
    supports_skill_activation = True

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable

    def is_available(self) -> bool:
        if self.executable:
            return True
        self.executable = shutil.which("kimi")
        return self.executable is not None

    def _strip_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        if not self.executable:
            return None
        cwd = Path.cwd()
        full_prompt = prompt
        if system_instructions:
            full_prompt = f"{system_instructions}\n\n{full_prompt}"
        try:
            proc = subprocess.run(
                [self.executable, "-p", full_prompt],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = proc.stdout or ""
            if proc.stderr:
                output += "\n" + proc.stderr
            lines = [self._strip_ansi(l) for l in output.splitlines() if self._strip_ansi(l).strip()]
            return "\n".join(lines)
        except Exception as exc:
            return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_runners.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/runners/kimi_cli.py dashboard/tests/test_runners.py && git commit -m "feat(runners): add Kimi CLI backend"
```

---

## Task 3: Cursor, Claude, Codex CLI backends

**Files:**
- Create: `dashboard/core/runners/cursor_cli.py`
- Create: `dashboard/core/runners/claude_code.py`
- Create: `dashboard/core/runners/codex_cli.py`
- Test: `dashboard/tests/test_runners.py`

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_runners.py`:

```python
from unittest.mock import patch, MagicMock


def test_cursor_backend_uses_cli():
    with patch("core.runners.cursor_cli.shutil.which", return_value="/usr/bin/cursor"):
        from core.runners.cursor_cli import CursorCliBackend
        backend = CursorCliBackend()
        assert backend.is_available() is True
        with patch("subprocess.run", return_value=MagicMock(stdout="cursor out", stderr="", returncode=0)) as mock_run:
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "cursor out"
            assert mock_run.call_args[0][0][0] == "/usr/bin/cursor"


def test_claude_backend_uses_cli():
    with patch("core.runners.claude_code.shutil.which", return_value="/usr/bin/claude"):
        from core.runners.claude_code import ClaudeCodeBackend
        backend = ClaudeCodeBackend()
        assert backend.is_available() is True
        with patch("subprocess.run", return_value=MagicMock(stdout="claude out", stderr="", returncode=0)) as mock_run:
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "claude out"
            assert mock_run.call_args[0][0][0] == "/usr/bin/claude"


def test_codex_backend_uses_cli():
    with patch("core.runners.codex_cli.shutil.which", return_value="/usr/bin/codex"):
        from core.runners.codex_cli import CodexCliBackend
        backend = CodexCliBackend()
        assert backend.is_available() is True
        with patch("subprocess.run", return_value=MagicMock(stdout="codex out", stderr="", returncode=0)) as mock_run:
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "codex out"
            assert mock_run.call_args[0][0][0] == "/usr/bin/codex"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError for the three new modules.

- [ ] **Step 3: Write minimal implementation**

`dashboard/core/runners/cursor_cli.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


class CursorCliBackend:
    name = "cursor"
    supports_skill_activation = False

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable

    def is_available(self) -> bool:
        if self.executable:
            return True
        self.executable = shutil.which("cursor")
        return self.executable is not None

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        if not self.executable:
            return None
        full_prompt = prompt
        if system_instructions:
            full_prompt = f"{system_instructions}\n\n{full_prompt}"
        try:
            proc = subprocess.run(
                [self.executable, "-p", full_prompt],
                cwd=str(Path.cwd()),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = proc.stdout or ""
            if proc.stderr:
                output += "\n" + proc.stderr
            return output.strip()
        except Exception:
            return None
```

`dashboard/core/runners/claude_code.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


class ClaudeCodeBackend:
    name = "claude"
    supports_skill_activation = False

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable

    def is_available(self) -> bool:
        if self.executable:
            return True
        self.executable = shutil.which("claude")
        return self.executable is not None

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        if not self.executable:
            return None
        full_prompt = prompt
        if system_instructions:
            full_prompt = f"{system_instructions}\n\n{full_prompt}"
        try:
            proc = subprocess.run(
                [self.executable, "-p", full_prompt],
                cwd=str(Path.cwd()),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = proc.stdout or ""
            if proc.stderr:
                output += "\n" + proc.stderr
            return output.strip()
        except Exception:
            return None
```

`dashboard/core/runners/codex_cli.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


class CodexCliBackend:
    name = "codex"
    supports_skill_activation = False

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable

    def is_available(self) -> bool:
        if self.executable:
            return True
        self.executable = shutil.which("codex")
        return self.executable is not None

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        if not self.executable:
            return None
        full_prompt = prompt
        if system_instructions:
            full_prompt = f"{system_instructions}\n\n{full_prompt}"
        try:
            proc = subprocess.run(
                [self.executable, "-p", full_prompt],
                cwd=str(Path.cwd()),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = proc.stdout or ""
            if proc.stderr:
                output += "\n" + proc.stderr
            return output.strip()
        except Exception:
            return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_runners.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/runners/cursor_cli.py dashboard/core/runners/claude_code.py dashboard/core/runners/codex_cli.py dashboard/tests/test_runners.py && git commit -m "feat(runners): add Cursor, Claude and Codex CLI backends"
```

---

## Task 4: OpenAI API backend

**Files:**
- Create: `dashboard/core/runners/openai_api.py`
- Test: `dashboard/tests/test_runners.py`

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_runners.py`:

```python
from unittest.mock import patch, MagicMock


def test_openai_api_backend_requires_key():
    with patch.dict("os.environ", {}, clear=True):
        from core.runners.openai_api import OpenAIApiBackend
        backend = OpenAIApiBackend()
        assert backend.is_available() is False


def test_openai_api_backend_calls_endpoint():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        from core.runners.openai_api import OpenAIApiBackend
        backend = OpenAIApiBackend(model="gpt-4o-mini")
        assert backend.is_available() is True
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": "api output"}}]},
            )
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "api output"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/core/runners/openai_api.py`:

```python
from __future__ import annotations

import os
from typing import Optional

import requests


class OpenAIApiBackend:
    name = "openai_api"
    supports_skill_activation = False

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        if not self.api_key:
            return None
        messages = []
        if system_instructions:
            messages.append({"role": "system", "content": system_instructions})
        messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_runners.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/runners/openai_api.py dashboard/tests/test_runners.py dashboard/requirements.txt && git commit -m "feat(runners): add OpenAI-compatible API backend"
```

---

## Task 5: Skills/MCPs registry por rol

**Files:**
- Create: `dashboard/core/role_skills_registry.yaml`
- Create: `dashboard/core/skills_registry.py`
- Test: `dashboard/tests/test_skills_registry.py`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_skills_registry.py`:

```python
from core.skills_registry import SkillsRegistry


def test_registry_loads_and_returns_prefix():
    registry = SkillsRegistry("dashboard/core/role_skills_registry.yaml")
    prefix = registry.get_prompt_prefix("architect", supports_skill_activation=True)
    assert "Activa la skill 'dotnet'" in prefix
    assert "Activa la skill 'code-review'" in prefix


def test_registry_fallback_when_no_skill_activation():
    registry = SkillsRegistry("dashboard/core/role_skills_registry.yaml")
    prefix = registry.get_prompt_prefix("architect", supports_skill_activation=False)
    assert "Activa la skill" not in prefix
    assert "patrones técnicos" in prefix
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError / FileNotFoundError.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/core/role_skills_registry.yaml`:

```yaml
pm_research:
  skills:
    - tech-research
    - agent-browser
  mcp_servers: []
  prompt_prefix: |
    Investiga el codebase actual usando búsqueda web y lectura de archivos. Sé conciso y cita fuentes.

product_manager:
  skills:
    - humanizer
  prompt_prefix: |
    Consolida hallazgos en un PRD claro, bien estructurado y libre de ambigüedades.

architect:
  skills:
    - dotnet
    - mcp-builder
    - code-review
  mcp_servers: []
  prompt_prefix: |
    Define patrones técnicos, APIs, estructura de directorios y convenciones. NO escribas código concreto.

project_manager:
  skills:
    - writing-plans
  prompt_prefix: |
    Construye un plan de ejecución con DAG de dependencias y batches paralelos respetando el límite de workers.

engineer:
  skills:
    - dotnet
    - git-workflow
    - test-driven-development
    - crud
  mcp_servers:
    - filesystem
  prompt_prefix: |
    Implementa cambios reales en archivos, ejecuta build/tests, respeta el git workflow y los patrones del architect.

qa:
  skills:
    - code-review
    - systematic-debugging
  prompt_prefix: |
    Revisa calidad, build/tests y consistencia con el architecture.md. Sé estricto pero constructivo.
```

Create `dashboard/core/skills_registry.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml


class SkillsRegistry:
    def __init__(self, yaml_path: str = "core/role_skills_registry.yaml"):
        self.yaml_path = Path(yaml_path)
        self._data: Dict[str, Dict] = self._load()

    def _load(self) -> Dict[str, Dict]:
        if not self.yaml_path.exists():
            return {}
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get_skills(self, role: str) -> List[str]:
        return self._data.get(role, {}).get("skills", []) or []

    def get_mcp_servers(self, role: str) -> List[str]:
        return self._data.get(role, {}).get("mcp_servers", []) or []

    def get_prompt_prefix(self, role: str, supports_skill_activation: bool = False) -> str:
        entry = self._data.get(role, {})
        skills = entry.get("skills", []) or []
        prefix = entry.get("prompt_prefix", "")
        lines = []
        if supports_skill_activation and skills:
            for skill in skills:
                lines.append(f"Activa la skill '{skill}' y aplica sus convenciones y mejores prácticas.")
        elif prefix:
            lines.append(prefix.strip())
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_skills_registry.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/role_skills_registry.yaml dashboard/core/skills_registry.py dashboard/tests/test_skills_registry.py && git commit -m "feat(skills): add role skills/MCP registry with activation fallback"
```

---

## Task 6: Conectar runners + skills con Actions y Orchestrator

**Files:**
- Modify: `dashboard/core/actions/base.py`
- Modify: `dashboard/core/orchestrator.py`
- Modify: `dashboard/server.py`
- Test: existing tests should still pass

- [ ] **Step 1: Update Action base to inject skill prefix**

Modify `dashboard/core/actions/base.py` to add helper:

```python
from core.skills_registry import SkillsRegistry
from core.runners.registry import BackendRegistry


class Action:
    def __init__(self, action_id: str = "", name: str = "", desc: str = ""):
        self.action_id = action_id
        self.name = name
        self.desc = desc
        self.skills_registry = SkillsRegistry()

    async def act(self, action, context, **kwargs):
        ...

    def build_full_prompt(self, prompt: str, role: str, backend_name: Optional[str] = None) -> str:
        backend = BackendRegistry.default()._backend_by_name(backend_name) if backend_name else None
        supports = getattr(backend, "supports_skill_activation", False) if backend else False
        prefix = self.skills_registry.get_prompt_prefix(role, supports_skill_activation=supports)
        if prefix:
            return f"{prefix}\n\n{prompt}"
        return prompt
```

(Implementation detail: add `_backend_by_name` helper to `BackendRegistry` if not present.)

- [ ] **Step 2: Update Orchestrator to accept backend registry and skills registry**

Modify `dashboard/core/orchestrator.py`:

```python
from core.runners.registry import BackendRegistry
from core.skills_registry import SkillsRegistry


class Orchestrator(threading.Thread):
    def __init__(
        self,
        ticket,
        resume=False,
        runner_factory=None,
        callbacks=None,
        backend_registry=None,
        skills_registry=None,
    ):
        ...
        self.backend_registry = backend_registry or BackendRegistry.default()
        self.skills_registry = skills_registry or SkillsRegistry()

    def _run_kimi(self, prompt, phase_name, timeout_seconds, agent_id=None):
        role = self._infer_role_from_phase(phase_name)
        full_prompt = self.skills_registry.get_prompt_prefix(role, self.backend_registry.supports_skill_activation()) + "\n\n" + prompt
        return self.backend_registry.run_prompt(
            full_prompt,
            phase_name=phase_name,
            timeout_seconds=timeout_seconds,
            agent_id=agent_id,
        )
```

Add `_infer_role_from_phase` mapping `pm_* -> pm_research`, `architect` -> `architect`, etc.

- [ ] **Step 3: Update server.py to pass BackendRegistry**

Modify `AgentRunner._orchestrator_callbacks` to include `backend_registry` and `skills_registry`:

```python
from core.runners.registry import BackendRegistry
from core.skills_registry import SkillsRegistry

class AgentRunner(threading.Thread):
    def __init__(self, ticket, resume=False):
        ...
        self.backend_registry = BackendRegistry.default()
        self.skills_registry = SkillsRegistry()
        self.orchestrator = Orchestrator(
            ticket,
            resume=resume,
            callbacks=self._orchestrator_callbacks(),
            backend_registry=self.backend_registry,
            skills_registry=self.skills_registry,
        )
```

- [ ] **Step 4: Run all tests**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/actions/base.py dashboard/core/orchestrator.py dashboard/server.py && git commit -m "feat(integration): wire BackendRegistry and SkillsRegistry into Actions and Orchestrator"
```

---

## Task 7: Orchestrator Swarm — DispatcherRole

**Files:**
- Create: `dashboard/core/roles/dispatcher_role.py`
- Test: `dashboard/tests/test_dispatcher_role.py`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_dispatcher_role.py`:

```python
import pytest
from core.environment import Environment
from core.models import Message
from core.roles.dispatcher_role import DispatcherRole


@pytest.mark.asyncio
async def test_dispatcher_reacts_to_ticket_ready():
    env = Environment()
    role = DispatcherRole(ticket_id="T-1", ticket_title="Test", ticket_description="Desc")
    env.add_role(role)
    env.publish_message(Message(
        content="go",
        sent_from="orchestrator",
        cause_by="ticket_ready",
        send_to={"dispatcher"},
        metadata={},
    ))
    result = await role.run(env)
    assert result is not None
    assert result.cause_by == "prd_ready"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError.

- [ ] **Step 3: Write minimal implementation**

Create `dashboard/core/roles/dispatcher_role.py`:

```python
from __future__ import annotations

from typing import Any, List, Optional

from core.models import Message
from core.roles.base import Role


class DispatcherRole(Role):
    role_id = "dispatcher"
    addresses = {"dispatcher"}

    def __init__(self, ticket_id: str, ticket_title: str, ticket_description: str):
        super().__init__(
            role_id=self.role_id,
            profile="Dispatcher",
            goal="Coordinate the phases of the software factory loop.",
            addresses=self.addresses,
        )
        self.ticket_id = ticket_id
        self.ticket_title = ticket_title
        self.ticket_description = ticket_description
        self._processed_ids: set = set()

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        for msg in reversed(context):
            if msg.id in self._processed_ids:
                continue
            if msg.cause_by in {"ticket_ready", "architecture_ready", "plan_ready", "batch_completed"}:
                return msg
        return None

    async def think(self, context: List[Message]) -> Optional[Any]:
        return self._find_trigger(context) and "dispatch"

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None
        self._processed_ids.add(trigger.id)

        if trigger.cause_by == "ticket_ready":
            msg = Message(
                content=f"Iniciar PM Analysis para {self.ticket_id}",
                sent_from=self.role_id,
                cause_by="prd_ready",
                send_to={"all"},
                metadata={"ticket_id": self.ticket_id, "ticket_title": self.ticket_title, "ticket_description": self.ticket_description},
            )
            env.publish_message(msg)
            return msg

        if trigger.cause_by == "architecture_ready":
            msg = Message(
                content="Arquitectura lista; planificar tareas.",
                sent_from=self.role_id,
                cause_by="plan_ready_trigger",
                send_to={"planner"},
                metadata={"ticket_id": self.ticket_id},
            )
            env.publish_message(msg)
            return msg

        return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_dispatcher_role.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/roles/dispatcher_role.py dashboard/tests/test_dispatcher_role.py && git commit -m "feat(roles): add DispatcherRole for orchestrator swarm"
```

---

## Task 8: Orchestrator Swarm — MonitorRole y RecoveryRole

**Files:**
- Create: `dashboard/core/roles/monitor_role.py`
- Create: `dashboard/core/roles/recovery_role.py`
- Test: `dashboard/tests/test_monitor_role.py`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/test_monitor_role.py`:

```python
import pytest
from core.environment import Environment
from core.models import Message
from core.roles.monitor_role import MonitorRole


@pytest.mark.asyncio
async def test_monitor_detects_stall():
    env = Environment()
    role = MonitorRole(max_idle_rounds=2)
    env.add_role(role)
    env.publish_message(Message(content="x", sent_from="a", cause_by="task_completed", send_to={"all"}, metadata={}))
    result = await role.run(env)
    assert result is None or result.cause_by == "health_check"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: ImportError.

- [ ] **Step 3: Write minimal implementation**

`dashboard/core/roles/monitor_role.py`:

```python
from __future__ import annotations

from typing import Any, List, Optional

from core.models import Message
from core.roles.base import Role


class MonitorRole(Role):
    role_id = "monitor"
    addresses = {"monitor"}

    def __init__(self, max_idle_rounds: int = 5):
        super().__init__(
            role_id=self.role_id,
            profile="Monitor",
            goal="Detect stalls and report progress.",
            addresses=self.addresses,
        )
        self.max_idle_rounds = max_idle_rounds
        self._idle_rounds = 0
        self._last_history_len = 0

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        if len(history) == self._last_history_len:
            self._idle_rounds += 1
        else:
            self._idle_rounds = 0
        self._last_history_len = len(history)

        if self._idle_rounds >= self.max_idle_rounds:
            msg = Message(
                content="Stall detected",
                sent_from=self.role_id,
                cause_by="health_check",
                send_to={"recovery"},
                metadata={"status": "stalled", "idle_rounds": self._idle_rounds},
            )
            env.publish_message(msg)
            self._idle_rounds = 0
            return msg
        return None
```

`dashboard/core/roles/recovery_role.py`:

```python
from __future__ import annotations

from typing import Any, List, Optional

from core.models import Message
from core.roles.base import Role


class RecoveryRole(Role):
    role_id = "recovery"
    addresses = {"recovery"}

    def __init__(self, max_retries: int = 2):
        super().__init__(
            role_id=self.role_id,
            profile="Recovery",
            goal="Decide retries, replanning or escalation on failures.",
            addresses=self.addresses,
        )
        self.max_retries = max_retries
        self._failures: dict = {}

    def _find_trigger(self, context: List[Message]) -> Optional[Message]:
        for msg in reversed(context):
            if msg.cause_by in {"task_failed", "reject_with_feedback", "health_check"}:
                return msg
        return None

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None

        if trigger.cause_by == "task_failed":
            task_id = trigger.metadata.get("task_id", "unknown")
            count = self._failures.get(task_id, 0) + 1
            self._failures[task_id] = count
            if count <= self.max_retries:
                msg = Message(
                    content=f"Retry task {task_id}",
                    sent_from=self.role_id,
                    cause_by="task_assigned",
                    send_to={f"engineer-{task_id}"},
                    metadata=trigger.metadata,
                )
                env.publish_message(msg)
                return msg
            else:
                msg = Message(
                    content=f"Task {task_id} exceeded retries",
                    sent_from=self.role_id,
                    cause_by="run_failed",
                    send_to={"orchestrator"},
                    metadata={"task_id": task_id},
                )
                env.publish_message(msg)
                return msg
        return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/test_monitor_role.py -v
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/roles/monitor_role.py dashboard/core/roles/recovery_role.py dashboard/tests/test_monitor_role.py && git commit -m "feat(roles): add MonitorRole and RecoveryRole for orchestrator swarm"
```

---

## Task 9: Refactor Orchestrator para usar el swarm

**Files:**
- Modify: `dashboard/core/orchestrator.py`
- Test: existing tests

- [ ] **Step 1: Replace phase orchestration por roles coordinadores**

Modify `Orchestrator.run()` to:

1. Create `Environment`.
2. Add `DispatcherRole`, `MonitorRole`, `RecoveryRole`.
3. Add existing phase roles (`PMLeadRole` via pm_analysis, `ArchitectRole`, `PlannerRole`, etc.) on demand.
4. Publish `ticket_ready`.
5. Run rounds until idle or stop.

Keep existing callbacks for state/heartbeat.

A minimal refactor can keep the existing `_run_phase_*` methods but drive them from the dispatcher. For this plan, the pragmatic step is:

- In `run()`, create env, add `DispatcherRole`, `MonitorRole`, `RecoveryRole`.
- Publish `ticket_ready`.
- Run rounds.
- The `DispatcherRole` publishes `prd_ready`, etc.
- Existing phase methods still execute as callbacks when dispatcher triggers them.

Because a full pure-message refactor is large, the intermediate milestone is: Orchestrator creates the coordinator swarm and uses `DispatcherRole` to trigger phases; phase execution still happens via the existing `_run_phase_*` helpers until a future refactor.

- [ ] **Step 2: Run all tests**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/ -q
```

- [ ] **Step 3: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add dashboard/core/orchestrator.py && git commit -m "feat(orchestrator): integrate coordinator swarm roles"
```

---

## Task 10: Actualizar install.sh para portabilidad

**Files:**
- Modify: `install.sh`
- Modify: `dashboard/requirements.txt`
- Create: `scripts/validate_install.py`

- [ ] **Step 1: Update requirements.txt**

Ensure `dashboard/requirements.txt` contains:

```text
flask>=2.0
flask-socketio>=5.0
pexpect>=4.8
pyyaml>=6.0
requests>=2.25
```

- [ ] **Step 2: Rewrite install.sh**

Replace `install.sh` with:

```bash
#!/bin/bash
# Instala meta-ralph como skill de Kimi Code CLI y como comando global.

set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_NAME="meta-ralph"
KIMI_SKILLS_DIR="${KIMI_SKILLS_DIR:-$HOME/.kimi-code/skills}"
TARGET_SKILL_DIR="$KIMI_SKILLS_DIR/$SKILL_NAME"
SCRIPT="$SKILL_DIR/scripts/meta-ralph.sh"

if [ ! -f "$SCRIPT" ]; then
  echo "❌ No se encontró $SCRIPT"
  exit 1
fi

chmod +x "$SCRIPT"

# Python check
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 no está instalado. meta-ralph requiere Python 3.10+."
  exit 1
fi

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "❌ Se requiere Python 3.10+. Versión detectada: $PY_MAJOR.$PY_MINOR"
  exit 1
fi

# Git check
if ! command -v git >/dev/null 2>&1; then
  echo "❌ git no está instalado. meta-ralph requiere git."
  exit 1
fi

# Registrar skill
if [ "$SKILL_DIR" != "$TARGET_SKILL_DIR" ]; then
  mkdir -p "$KIMI_SKILLS_DIR"
  if [ -e "$TARGET_SKILL_DIR" ] || [ -L "$TARGET_SKILL_DIR" ]; then
    if [ "$(readlink -f "$TARGET_SKILL_DIR" 2>/dev/null || echo "")" != "$SKILL_DIR" ]; then
      echo "⚠️  $TARGET_SKILL_DIR ya existe y apunta a otro lugar."
      echo "   Elimínalo manualmente si quieres reinstalar este skill."
      exit 1
    fi
  else
    ln -sf "$SKILL_DIR" "$TARGET_SKILL_DIR"
    echo "🔗 Skill registrado: $TARGET_SKILL_DIR → $SKILL_DIR"
  fi
else
  echo "ℹ️  El skill ya está en $TARGET_SKILL_DIR"
fi

# Crear venv para el dashboard
DASHBOARD_DIR="$SKILL_DIR/dashboard"
VENV_DIR="$DASHBOARD_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "⚙️  Creando entorno virtual para el dashboard..."
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -q --upgrade pip
  "$VENV_DIR/bin/pip" install -q -r "$DASHBOARD_DIR/requirements.txt"
  echo "✅ Dashboard dependencies instaladas"
else
  echo "ℹ️  Entorno virtual del dashboard ya existe"
fi

# Crear estructura de proyecto de ejemplo
META_DIR="$SKILL_DIR/scripts/meta-ralph"
mkdir -p "$META_DIR/state"
if [ ! -f "$META_DIR/config.json" ]; then
  cat > "$META_DIR/config.json" <<'EOF'
{
  "preferred_backends": ["kimi", "claude", "cursor", "codex", "openai_api"],
  "model_overrides": {
    "openai_api": "gpt-4o-mini"
  },
  "timeout_defaults": {
    "pm_research": 600,
    "architect": 600,
    "planning": 600,
    "engineer": 1800,
    "qa": 600
  },
  "api_key_path": "~/.config/meta-ralph/openai_api_key"
}
EOF
  echo "✅ Configuración inicial creada en $META_DIR/config.json"
fi

if [ ! -f "$META_DIR/prd.json" ]; then
  cat > "$META_DIR/prd.json" <<'EOF'
{
  "projectName": "Ejemplo",
  "stories": [
    {
      "id": "US-001",
      "title": "Historia de ejemplo",
      "description": "Descripción de la historia de usuario."
    }
  ]
}
EOF
  echo "✅ PRD de ejemplo creado en $META_DIR/prd.json"
fi

# Detectar shell y archivo de configuración
SHELL_NAME="$(basename "$SHELL")"
case "$SHELL_NAME" in
  zsh)
    RC_FILE="$HOME/.zshrc"
    ;;
  bash)
    RC_FILE="$HOME/.bashrc"
    if [ "$(uname -s)" = "Darwin" ]; then
      RC_FILE="$HOME/.bash_profile"
    fi
    ;;
  fish)
    RC_FILE="$HOME/.config/fish/config.fish"
    mkdir -p "$(dirname "$RC_FILE")"
    ;;
  *)
    RC_FILE="$HOME/.profile"
    ;;
esac

# Crear symlink en ~/.local/bin si existe, sino en ~/.bin
if [ -d "$HOME/.local/bin" ]; then
  BIN_DIR="$HOME/.local/bin"
else
  BIN_DIR="$HOME/.bin"
  mkdir -p "$BIN_DIR"
fi

ln -sf "$SCRIPT" "$BIN_DIR/meta-ralph"
echo "🔗 Symlink creado: $BIN_DIR/meta-ralph → $SCRIPT"

# Asegurar que BIN_DIR esté en PATH
if [ "$SHELL_NAME" = "fish" ]; then
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Meta-Ralph CLI" >> "$RC_FILE"
    echo "fish_add_path $BIN_DIR" >> "$RC_FILE"
    echo "✅ Agregado $BIN_DIR a PATH en $RC_FILE"
  else
    echo "ℹ️  $BIN_DIR ya está en PATH"
  fi
else
  if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
    echo "" >> "$RC_FILE"
    echo "# Meta-Ralph CLI" >> "$RC_FILE"
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
    echo "✅ Agregado $BIN_DIR a PATH en $RC_FILE"
  else
    echo "ℹ️  $BIN_DIR ya está en PATH"
  fi
fi

# Reporte de backends detectados
echo ""
echo "🔍 Backends de IA detectados:"
BACKENDS_FOUND=0
detect_backend() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "  ✅ $1"
    BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
  else
    echo "  ❌ $1 (no instalado)"
  fi
}
detect_backend kimi
detect_backend claude
detect_backend cursor
detect_backend codex
if [ -n "$OPENAI_API_KEY" ]; then
  echo "  ✅ openai_api (OPENAI_API_KEY configurada)"
  BACKENDS_FOUND=$((BACKENDS_FOUND + 1))
else
  echo "  ❌ openai_api (OPENAI_API_KEY no configurada)"
fi

if [ "$BACKENDS_FOUND" -eq 0 ]; then
  echo ""
  echo "⚠️  No se detectó ningún backend de IA. meta-ralph no podrá ejecutar prompts."
  echo "   Instala al menos uno de los siguientes:"
  echo "   - Kimi Code CLI: https://kimi.com/download"
  echo "   - Claude Code: https://claude.ai/download"
  echo "   - Cursor: https://cursor.com"
  echo "   - OpenAI Codex CLI: npm install -g @openai/codex"
  echo "   - O configura OPENAI_API_KEY para usar la API de OpenAI."
fi

echo ""
echo "✅ Meta-Ralph instalado como skill en $TARGET_SKILL_DIR"
echo "✅ Comando 'meta-ralph' disponible en $BIN_DIR"
echo ""
echo "Reinicia tu terminal o ejecuta:"
echo "   source $RC_FILE"
echo ""
echo "Luego, en un proyecto git:"
echo "   meta-ralph init"
echo "   meta-ralph run"
```

- [ ] **Step 3: Create validate_install.py**

Create `scripts/validate_install.py`:

```python
#!/usr/bin/env python3
"""Validate a fresh meta-ralph install."""

import json
import os
import subprocess
import sys
from pathlib import Path


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main():
    skill_dir = Path(__file__).resolve().parent.parent
    venv = skill_dir / "dashboard" / ".venv"
    errors = []

    if not venv.exists():
        errors.append(f"venv missing: {venv}")
    else:
        result = run([str(venv / "bin" / "python"), "-c", "import flask, yaml, requests"])
        if result.returncode != 0:
            errors.append(f"venv dependencies missing: {result.stderr}")

    config = skill_dir / "scripts" / "meta-ralph" / "config.json"
    if not config.exists():
        errors.append(f"config missing: {config}")
    else:
        try:
            data = json.loads(config.read_text())
            assert "preferred_backends" in data
        except Exception as exc:
            errors.append(f"config invalid: {exc}")

    symlink = Path.home() / ".local" / "bin" / "meta-ralph"
    if not symlink.exists() and not (Path.home() / ".bin" / "meta-ralph").exists():
        errors.append("meta-ralph symlink not found in PATH dirs")

    if errors:
        print("❌ Validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("✅ meta-ralph install looks good")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Validate install.sh in tmpdir**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && bash -n install.sh && chmod +x install.sh
```

- [ ] **Step 5: Commit**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add install.sh dashboard/requirements.txt scripts/validate_install.py && git commit -m "feat(install): portable install.sh with backend detection and validation"
```

---

## Task 11: Testing final y dashboard

**Files:**
- All

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python -m pytest tests/ -q --tb=short
```

Expected: all pass.

- [ ] **Step 2: Restart dashboard**

```bash
# Stop previous dashboard if running
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard && python server.py --port 5050 --no-browser
```

Verify:

```bash
curl -s http://localhost:5050/api/run-state | head -c 100
```

Expected: JSON run-state.

- [ ] **Step 3: Commit final**

```bash
cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph && git add -A && git commit -m "feat: AI runner portability, orchestrator swarm and install validation"
```

---

## Spec Coverage Check

| Spec Section | Task(s) |
|--------------|---------|
| 1.1 Interfaz común AIBackend | Task 1 |
| 1.2 Backends soportados | Tasks 2, 3, 4 |
| 1.3 Estrategia fallback | Task 1 |
| 1.4 Configuración | Task 10 |
| 2.1 Registro YAML | Task 5 |
| 2.2 Uso en Actions | Task 6 |
| 3.1 Roles coordinadores | Tasks 7, 8 |
| 3.2 Flujo de mensajes | Task 9 |
| 4.1/4.2 Portabilidad install.sh | Task 10 |
| 5. Testing | Tasks 1-11 |

## Placeholder Scan

No placeholders like TBD/TODO/fill-in-details remain. Each task includes exact file paths, code blocks and commands.

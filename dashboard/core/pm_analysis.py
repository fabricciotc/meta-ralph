#!/usr/bin/env python3
"""Product Management Analysis phase for meta-ralph.

Self-contained PM research/consolidation logic that can be used both by the
legacy AgentRunner and by the new MetaGPT-style Orchestrator. It depends only
on the stdlib plus the core Message/Memory/Environment/Role/Action classes.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.environment import Environment
from core.models import Message
from core.roles.pm_lead_role import PMLeadRole
from core.roles.pm_research_role import PMResearchRole


# Default subagents used during PM Analysis.
DEFAULT_SUBAGENTS: List[tuple[str, str, str]] = [
    ("pm-domain", "Domain Analyst", "dominio de negocio, entidades, reglas y flujos principales"),
    ("pm-ux", "UX Researcher", "experiencia de usuario, vistas, flujos de pantalla y validaciones de frontend"),
    ("pm-technical", "Technical Analyst", "stack técnico, arquitectura, patrones y decisiones técnicas"),
    ("pm-integration", "Integration Analyst", "integraciones con APIs de terceros, bases de datos y servicios externos"),
    ("pm-risk", "Risk Analyst", "riesgos, seguridad, compliance, permisos y manejo de errores"),
]


def get_meta_dir(cwd: Optional[Path] = None) -> Path:
    """Return the meta-ralph scripts directory relative to the project."""
    return (cwd or Path.cwd()) / "scripts" / "meta-ralph"


def find_kimi_cli() -> Optional[str]:
    """Locate the Kimi CLI executable on PATH."""
    return shutil.which("kimi")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences."""
    import re

    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def run_kimi_prompt(
    prompt: str,
    phase_name: str = "Agent",
    timeout_seconds: int = 120,
    agent_id: Optional[str] = None,
    ticket_id: str = "",
    repo_path: Optional[str] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Optional[str]:
    """Execute a prompt with the Kimi CLI in prompt mode (-p).

    Mirrors the legacy AgentRunner._run_kimi_prompt behaviour but without
    depending on server.py state helpers.
    """
    import os

    safe_phase = phase_name.lower().replace(" ", "-")
    meta_dir = get_meta_dir()
    output_path = meta_dir / "state" / f"output-{ticket_id}-{safe_phase}.txt"
    prompt_path = meta_dir / "state" / f"prompt-{ticket_id}-{safe_phase}.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    prompt_path.write_text(prompt, encoding="utf-8")

    def log(message: str, level: str = "info"):
        if log_callback:
            log_callback(message, level)

    kimi = find_kimi_cli()
    if not kimi:
        log("No se encontró el ejecutable de Kimi.", "error")
        return None

    log(f"Ejecutando Kimi -p para {phase_name} (timeout {timeout_seconds}s)...")
    dotnet_prefix = (
        "Activa la skill 'dotnet' y aplica sus convenciones y mejores prácticas "
        "a todo el código .NET que generes. "
    )
    full_prompt = dotnet_prefix + prompt

    cwd = repo_path or os.getcwd()
    try:
        proc = subprocess.run(
            [kimi, "-p", full_prompt],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        output = proc.stdout or ""
        if proc.stderr:
            output += "\n" + proc.stderr

        output_path.write_text(output, encoding="utf-8")

        if proc.returncode != 0:
            log(f"{phase_name} finalizó con código {proc.returncode}", "warning")

        lines = [strip_ansi(l) for l in output.splitlines() if strip_ansi(l).strip()]
        for line in lines[-50:]:
            log(f"[{phase_name}] {line[:250]}")

        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        log(f"{phase_name} excedió el tiempo límite ({timeout_seconds}s)", "error")
        return None
    except Exception as exc:
        log(f"{phase_name} error: {exc}", "error")
        return None


def decision_request_instruction() -> str:
    """Return the standard instruction appended to PM prompts."""
    return (
        "\n\nSi detectas decisiones de diseño que deban ser confirmadas por el usuario, "
        "lista las opciones claramente al final bajo el encabezado 'DECISIONES PENDIENTES:'."
    )


def build_pm_subagent_prompt(
    sub_id: str,
    focus: str,
    title: str,
    description: str,
    follow_up: Optional[str] = None,
) -> str:
    """Build the research prompt for a PM subagent."""
    role_name = {
        "pm-domain": "Domain Analyst",
        "pm-ux": "UX Researcher",
        "pm-technical": "Technical Analyst",
        "pm-integration": "Integration Analyst",
        "pm-risk": "Risk Analyst",
    }.get(sub_id, sub_id)

    follow_up_section = ""
    if follow_up:
        follow_up_section = (
            "\n\nEL PM LEAD TE HA PEDIDO AMPLIAR TU ANÁLISIS CON ESTA PREGUNTA/CLARIFICACIÓN:\n"
            f"{follow_up}\n\n"
            "Responde directamente a la solicitud del PM Lead, manteniendo el mismo formato de salida."
        )

    return (
        f"Eres el {role_name} de AgentFlow, una software factory estilo MetaGPT con múltiples agentes. "
        f"Tu enfoque exclusivo es: {focus}. "
        "Investiga el codebase del proyecto actual SOLO desde el ángulo que te corresponde. "
        "NO implementes código; solo investiga, analiza y documenta hallazgos. "
        "Sé conciso pero completo; prioriza calidad sobre extensión.\n\n"
        "Tu salida debe ser un markdown con estas secciones:\n"
        "1. Hallazgos clave (máximo 10 bullets).\n"
        "2. Requisitos funcionales / no funcionales relevantes a tu área.\n"
        "3. Riesgos, supuestos o preguntas abiertas.\n"
        "4. Archivos o áreas del codebase relevantes.\n\n"
        f"TICKET:\nTÍTULO: {title}\nDESCRIPCIÓN: {description}"
        + follow_up_section
        + "\n\nResponde en español."
        + decision_request_instruction()
    )


def build_pm_consolidator_prompt(
    title: str,
    description: str,
    research_files: Dict[str, Path],
    prd_path: Path,
) -> str:
    """Build the prompt that consolidates PM research into a PRD."""
    research_content = ""
    for sid, path in research_files.items():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[:150]
            research_content += f"\n\n--- {sid} ---\n\n" + "\n".join(lines)
        except Exception as exc:
            research_content += f"\n\n--- {sid} ---\n\nError leyendo hallazgos: {exc}"

    return (
        "Eres el Lead Product Manager de AgentFlow. Cinco PM Research Agents investigaron un ticket. "
        "Consolida SUS HALLAZGOS en un Product Requirements Document (PRD) conciso y accionable. "
        "NO inventes requisitos que no aparezcan en los hallazgos; tu trabajo es sintetizar lo que ya se investigó.\n\n"
        f"TICKET:\nTÍTULO: {title}\nDESCRIPCIÓN: {description}\n\n"
        "HALLAZGOS DE LOS AGENTES:\n" + research_content + "\n\n"
        "Genera un PRD en markdown con estas secciones (conciso, máximo 2 párrafos por sección):\n"
        "1. Resumen ejecutivo\n"
        "2. Requisitos funcionales principales (numerados, con prioridad Alta/Media/Baja)\n"
        "3. Requisitos no funcionales clave\n"
        "4. User stories y criterios de aceptación\n"
        "5. Tareas técnicas sugeridas con dependencias y estimaciones (S/M/L)\n"
        "6. Riesgos, supuestos y preguntas abiertas\n\n"
        f"Escribe el PRD completo en formato markdown en este archivo: {prd_path}\n\n"
        "Responde en español. Al final confirma brevemente que guardaste el PRD."
        + decision_request_instruction()
    )


def parse_clarifications(output: str) -> Dict[str, str]:
    """Parse clarification requests from consolidator output."""
    clarifications: Dict[str, str] = {}
    marker = "CLARIFICACIONES:"
    idx = output.find(marker)
    if idx == -1:
        return clarifications
    block = output[idx + len(marker):]
    next_header = block.find("\n#")
    if next_header != -1:
        block = block[:next_header]
    valid_ids = {"pm-domain", "pm-ux", "pm-technical", "pm-integration", "pm-risk"}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("*"):
            continue
        if ":" in line:
            sub_id, question = line.split(":", 1)
            sub_id = sub_id.strip()
            question = question.strip()
            if sub_id in valid_ids and question:
                clarifications[sub_id] = question
    return clarifications


def extract_prd_from_output(output: str, title: str, description: str) -> str:
    """Extract the PRD markdown from raw Kimi output."""
    lines = output.splitlines()
    prd_lines: List[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# PRD") or stripped.startswith("# 1.") or stripped.startswith("## 1."):
            capture = True
        if capture:
            prd_lines.append(line)
    if prd_lines:
        return "\n".join(prd_lines)

    filtered: List[str] = []
    for line in lines:
        if any(skip in line for skip in ["K2.7 Code", "context:", "yolo", "MCP server", "thinking...", "working...", "Welcome to Kimi"]):
            continue
        filtered.append(line)
    return f"# PRD Detallado: {title}\n\n**Descripción original:**\n\n{description}\n\n---\n\n" + "\n".join(filtered[-200:])


def write_fallback_prd(prd_path: Path, title: str, description: str) -> str:
    """Generate a minimal fallback PRD locally."""
    content = (
        f"# PRD: {title}\n\n"
        f"**Descripción:** {description}\n\n"
        "## Requisitos funcionales\n"
        "1. Implementar la funcionalidad solicitada.\n\n"
        "## Criterios de aceptación\n"
        "- El sistema satisface la descripción del ticket.\n\n"
        "## Tareas técnicas sugeridas\n"
        "- Analizar requisitos.\n"
        "- Implementar cambios.\n"
        "- Validar con tests.\n"
    )
    prd_path.write_text(content, encoding="utf-8")
    return content


def run_pm_analysis(
    ticket: Dict[str, Any],
    run_kimi: Optional[Callable[..., Optional[str]]] = None,
    max_rounds: int = 10,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Optional[Path]:
    """Execute PM Analysis using MetaGPT-style roles and return the PRD path.

    Args:
        ticket: Ticket dict with at least 'id', 'title', 'description' and optionally 'repoPath'.
        run_kimi: Function to invoke Kimi. Defaults to run_kimi_prompt.
        max_rounds: Maximum environment rounds to avoid infinite loops.
        log_callback: Optional callback(message, level) for logging.

    Returns:
        Path to the generated PRD, or None if generation failed.
    """
    ticket_id = ticket.get("id", "")
    title = ticket.get("title", "")
    description = ticket.get("description", "")
    repo_path = ticket.get("repoPath")

    prd_path = get_meta_dir() / "state" / f"prd-{ticket_id}.md"
    prd_path.parent.mkdir(parents=True, exist_ok=True)

    pm_research_dir = get_meta_dir() / "state" / "pm-research"
    pm_research_dir.mkdir(parents=True, exist_ok=True)

    if prd_path.exists() and prd_path.stat().st_size > 100:
        if log_callback:
            log_callback(f"PRD pre-generado encontrado en {prd_path}; saltando PM Research.", "info")
        return prd_path

    env = Environment()

    kimi_runner = run_kimi or (
        lambda prompt, phase_name, timeout_seconds, agent_id=None: run_kimi_prompt(
            prompt,
            phase_name=phase_name,
            timeout_seconds=timeout_seconds,
            agent_id=agent_id,
            ticket_id=ticket_id,
            repo_path=repo_path,
            log_callback=log_callback,
        )
    )

    subagents = DEFAULT_SUBAGENTS

    def update_agent(agent_id: str, **kwargs):
        status = kwargs.get("status", "")
        progress = kwargs.get("progress", "")
        log = kwargs.get("log", "")
        if log_callback:
            log_callback(f"[{agent_id}] {status} {progress}% — {log}", "info")

    def build_prompt(sub_id: str, focus: str, title: str, description: str, follow_up: Optional[str]) -> str:
        return build_pm_subagent_prompt(sub_id, focus, title, description, follow_up)

    def build_consolidator_prompt(title: str, description: str, research_files: Dict[str, Path], prd_path: Path) -> str:
        return build_pm_consolidator_prompt(title, description, research_files, prd_path)

    for sub_id, sub_name, focus in subagents:
        role = PMResearchRole(sub_id, sub_name, focus)
        role.run_kimi = kimi_runner
        env.add_role(role)

    lead = PMLeadRole(
        run_kimi=kimi_runner,
        ticket_title=title,
        ticket_description=description,
        prd_path=prd_path,
        build_consolidator_prompt=build_consolidator_prompt,
        extract_prd=extract_prd_from_output,
        parse_clarifications=parse_clarifications,
        write_fallback_prd=write_fallback_prd,
        send_clarification=lambda sid, q: None,
        send_completion=lambda path, preview: None,
        subagents=[sid for sid, _, _ in subagents],
    )
    env.add_role(lead)

    env.publish_message(Message(
        content="Iniciar análisis de PM",
        sent_from="orchestrator",
        cause_by="research_request",
        send_to={"all"},
        metadata={
            "ticket_title": title,
            "ticket_description": description,
            "ticket_id": ticket_id,
            "output_dir": pm_research_dir,
            "build_prompt": build_prompt,
            "update_agent": update_agent,
            "phase_name": "pm_research",
            "timeout_seconds": 600,
        },
    ))

    for _ in range(max_rounds):
        active = asyncio.run(env.run_round())
        if not active and env.is_idle():
            break

    if prd_path.exists():
        return prd_path
    return None


if __name__ == "__main__":
    # Simple smoke test with mocked Kimi runner.
    tmpdir = tempfile.mkdtemp()
    original_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmpdir)
        (Path(tmpdir) / "scripts" / "meta-ralph" / "state").mkdir(parents=True)

        def mock_run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            if agent_id == "pm-research-agents":
                return "# PRD\n\nConsolidado."
            return f"# {agent_id}\n\nHallazgos."

        prd = run_pm_analysis(
            {"id": "SMOKE-001", "title": "Test", "description": "Desc"},
            run_kimi=mock_run_kimi,
        )
        assert prd is not None
        print("Smoke OK:", prd)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmpdir, ignore_errors=True)

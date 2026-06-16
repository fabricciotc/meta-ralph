#!/usr/bin/env python3
"""Demo del flujo PM Analysis con roles MetaGPT-style.

Ejecuta un análisis de PM end-to-end usando PMResearchRoles y PMLeadRole
sobre un Environment. Los llamados a Kimi están mockeados para que la demo
no dependa de una sesión de Kimi activa.

Uso:
    cd /Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard
    python demo_pm_roles.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.environment import Environment
from core.models import Message
from core.roles.pm_lead_role import PMLeadRole
from core.roles.pm_research_role import PMResearchRole


def main():
    tmpdir = tempfile.mkdtemp()
    try:
        output_dir = Path(tmpdir) / "pm-research"
        output_dir.mkdir(parents=True, exist_ok=True)
        prd_path = Path(tmpdir) / "prd.md"

        subagents = [
            ("pm-domain", "Domain Analyst", "dominio de negocio y reglas"),
            ("pm-ux", "UX Researcher", "experiencia de usuario y flujos"),
            ("pm-technical", "Technical Analyst", "stack técnico y arquitectura"),
            ("pm-integration", "Integration Analyst", "integraciones externas"),
            ("pm-risk", "Risk Analyst", "riesgos y seguridad"),
        ]

        research_calls = {sid: 0 for sid, _, _ in subagents}
        consolidation_calls = 0

        def run_kimi(prompt, phase_name, timeout_seconds, agent_id=None):
            if agent_id in research_calls:
                research_calls[agent_id] += 1
                return f"# Hallazgos de {agent_id}\n\nPunto clave para {agent_id}."
            if agent_id == "pm-research-agents":
                nonlocal consolidation_calls
                consolidation_calls += 1
                return (
                    "# PRD consolidado\n\n"
                    "## Resumen\n"
                    "Módulo de autenticación OAuth para Scord V3.\n\n"
                    "## Historias de usuario\n"
                    "- Login con Google\n"
                    "- Logout seguro\n"
                    "- Refresh de token\n"
                )
            return ""

        def update_agent(agent_id, **kwargs):
            status = kwargs.get("status", "")
            progress = kwargs.get("progress", "")
            log = kwargs.get("log", "")
            print(f"  [{agent_id}] {status} {progress}% — {log}")

        def build_prompt(sub_id, focus, title, description, follow_up):
            return f"Investiga {sub_id} ({focus}) para '{title}'"

        def build_consolidator_prompt(title, description, research_files, prd_path):
            return f"Consolida {list(research_files.keys())} en PRD para '{title}'"

        def extract_prd(output, title, description):
            return output

        def parse_clarifications(output):
            return {}

        def write_fallback_prd(prd_path, title, description):
            content = f"# Fallback PRD\n\n{title}\n\n{description}"
            Path(prd_path).write_text(content, encoding="utf-8")
            return content

        def send_completion(prd_path, preview):
            print(f"\n  ✅ PRD guardado en {prd_path}")
            print(f"     Preview: {preview[:120]}...")

        env = Environment()

        for sub_id, sub_name, focus in subagents:
            role = PMResearchRole(sub_id, sub_name, focus)
            role.run_kimi = run_kimi
            env.add_role(role)

        lead = PMLeadRole(
            run_kimi=run_kimi,
            ticket_title="Login OAuth",
            ticket_description="Agregar login con Google al sistema",
            prd_path=prd_path,
            build_consolidator_prompt=build_consolidator_prompt,
            extract_prd=extract_prd,
            parse_clarifications=parse_clarifications,
            write_fallback_prd=write_fallback_prd,
            send_clarification=lambda sid, q: print(f"  ❓ Clarificación para {sid}: {q}"),
            send_completion=send_completion,
            subagents=[sid for sid, _, _ in subagents],
        )
        env.add_role(lead)

        env.publish_message(Message(
            content="Iniciar análisis de PM",
            sent_from="orchestrator",
            cause_by="research_request",
            send_to={"all"},
            metadata={
                "ticket_title": "Login OAuth",
                "ticket_description": "Agregar login con Google al sistema",
                "ticket_id": "DEMO-OAUTH",
                "output_dir": output_dir,
                "build_prompt": build_prompt,
                "update_agent": update_agent,
                "phase_name": "pm_research",
                "timeout_seconds": 120,
            },
        ))

        print("\n🚀 Iniciando demo PM Analysis con roles MetaGPT-style\n")

        for i in range(10):
            print(f"— Ronda {i} —")
            active = asyncio.run(env.run_round())
            if not active and env.is_idle():
                break

        print(f"\n📊 Resumen:")
        print(f"   Rondas ejecutadas: {i + 1}")
        print(f"   Llamadas a research: {sum(research_calls.values())}")
        print(f"   Llamadas a consolidación: {consolidation_calls}")
        print(f"   PRD listo: {lead.prd_ready}")
        print(f"   PRD path: {prd_path}")

        if prd_path.exists():
            print(f"\n📝 Contenido del PRD:\n{prd_path.read_text(encoding='utf-8')[:500]}")
        else:
            print("\n⚠️  El PRD no fue generado.")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()

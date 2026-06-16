from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, List, Optional

from core.actions.base import Action
from core.models import Message


class ArchitectAction(Action):
    """Generates an architecture.md artifact from a PRD via the Kimi runner."""

    async def run(
        self,
        context: List[Message],
        run_kimi: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "prd_path",
            "architecture_path",
            "ticket_title",
            "ticket_description",
            "ticket_id",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"ArchitectAction missing required kwargs: {missing}")

        prd_path: Path = Path(kwargs["prd_path"])
        architecture_path: Path = Path(kwargs["architecture_path"])
        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        ticket_id: str = kwargs["ticket_id"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]
        review_answers: Optional[str] = kwargs.get("review_answers")

        build_prompt: Callable[..., str] = kwargs.get("build_architect_prompt") or self._build_default_prompt
        extract_architecture: Callable[..., str] = kwargs.get("extract_architecture") or self._extract_architecture

        architecture_path.parent.mkdir(parents=True, exist_ok=True)

        prd_content = prd_path.read_text(encoding="utf-8")

        if run_kimi is None:
            content = self._write_fallback_architecture(
                architecture_path,
                ticket_title,
                ticket_description,
                prd_content,
            )
            return Message(
                content=content,
                sent_from="architect",
                cause_by="architecture_ready",
                send_to={"orchestrator"},
                metadata={
                    "artifact": "architecture",
                    "path": str(architecture_path),
                    "fallback": True,
                    "ticket_id": ticket_id,
                    "ticket_title": ticket_title,
                    "ticket_description": ticket_description,
                },
            )

        prompt = build_prompt(
            ticket_title,
            ticket_description,
            prd_content,
            architecture_path,
            review_answers,
        )

        raw = run_kimi(prompt, phase_name, timeout_seconds, agent_id="architect")
        if inspect.isawaitable(raw):
            output = await raw
        else:
            output = raw

        if not output:
            content = self._write_fallback_architecture(
                architecture_path,
                ticket_title,
                ticket_description,
                prd_content,
            )
            fallback = True
        else:
            content = extract_architecture(output, ticket_title, ticket_description)
            fallback = False

        architecture_path.write_text(content, encoding="utf-8")

        return Message(
            content=content,
            sent_from="architect",
            cause_by="architecture_ready",
            send_to={"orchestrator"},
            metadata={
                "artifact": "architecture",
                "path": str(architecture_path),
                "fallback": fallback,
                "ticket_id": ticket_id,
                "ticket_title": ticket_title,
                "ticket_description": ticket_description,
            },
        )

    def _build_default_prompt(
        self,
        title: str,
        description: str,
        prd_content: str,
        architecture_path: Path,
        review_answers: Optional[str] = None,
    ) -> str:
        review_section = ""
        if review_answers:
            review_section = (
                "\n\nRESPUESTAS DEL DESIGN REVIEW (aplica estas decisiones):\n"
                f"{review_answers}\n"
            )

        return (
            "Eres el Arquitecto de AgentFlow, una software factory estilo MetaGPT. "
            "Diseña la arquitectura técnica global para el siguiente ticket. "
            "NO implementes código; define patrones, APIs, estructura de directorios, "
            "convenciones y decisiones técnicas que los engineers deberán seguir.\n\n"
            f"TICKET:\nTÍTULO: {title}\nDESCRIPCIÓN: {description}\n\n"
            f"PRD:\n{prd_content}\n\n"
            "Genera un documento de arquitectura en markdown con estas secciones:\n"
            "1. Resumen arquitectónico\n"
            "2. Decisiones técnicas principales\n"
            "3. Estructura de directorios y módulos recomendados\n"
            "4. APIs/interfaces y contratos\n"
            "5. Patrones y convenciones de código\n"
            "6. Riesgos y mitigaciones\n\n"
            f"Escribe el documento completo en formato markdown en este archivo: {architecture_path}\n\n"
            "Responde en español. Al final confirma brevemente que guardaste la arquitectura. "
            "Si detectas decisiones de diseño pendientes, listalas claramente bajo el encabezado "
            "'DECISIONES PENDIENTES:'."
            + review_section
        )

    def _extract_architecture(
        self,
        output: str,
        title: str,
        description: str,
    ) -> str:
        lines = output.splitlines()
        arch_lines: List[str] = []
        capture = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# Arquitectura") or stripped.startswith("# 1."):
                capture = True
            if capture:
                arch_lines.append(line)
        if arch_lines:
            return "\n".join(arch_lines)

        filtered: List[str] = []
        for line in lines:
            if any(
                skip in line
                for skip in [
                    "K2.7 Code",
                    "context:",
                    "yolo",
                    "MCP server",
                    "thinking...",
                    "working...",
                    "Welcome to Kimi",
                ]
            ):
                continue
            filtered.append(line)
        return f"# Arquitectura: {title}\n\n**Descripción:**\n\n{description}\n\n---\n\n" + "\n".join(filtered[-200:])

    def _write_fallback_architecture(
        self,
        architecture_path: Path,
        title: str,
        description: str,
        prd_content: str,
    ) -> str:
        content = (
            f"# Arquitectura: {title}\n\n"
            f"**Descripción:** {description}\n\n"
            "## Decisiones técnicas\n"
            "- Mantener el stack y patrones existentes del proyecto.\n\n"
            "## Estructura sugerida\n"
            "- Reutilizar módulos existentes; agregar componentes solo si el PRD lo indica.\n\n"
            "## Convenciones\n"
            "- Seguir las convenciones del proyecto y los patrones ya establecidos.\n\n"
            "## Notas del PRD\n"
            f"{prd_content[:500]}\n"
        )
        architecture_path.write_text(content, encoding="utf-8")
        return content

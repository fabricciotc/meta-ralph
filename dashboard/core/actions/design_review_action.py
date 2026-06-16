from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.models import Message


class DesignReviewAction(Action):
    """Generates design-review questions from an architecture document.

    When a Kimi runner is available, it returns a ``design_review_requested``
    message with the list of open questions. If no runner is provided, it
    returns a ``design_review_answered`` message with assumed default answers
    so the flow can continue autonomously.
    """

    async def run(
        self,
        context: List[Message],
        run_kimi: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "architecture_content",
            "ticket_title",
            "ticket_description",
            "ticket_id",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"DesignReviewAction missing required kwargs: {missing}")

        architecture_content: str = kwargs["architecture_content"]
        ticket_title: str = kwargs["ticket_title"]
        ticket_description: str = kwargs["ticket_description"]
        ticket_id: str = kwargs["ticket_id"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        build_prompt: Callable[..., str] = kwargs.get("build_design_review_prompt") or self._build_default_prompt
        parse_questions: Callable[..., List[str]] = kwargs.get("parse_design_questions") or self._parse_questions

        if run_kimi is None:
            answers = self._assumed_answers(architecture_content)
            content = "Respuestas asumidas para el design review:\n\n" + "\n".join(
                f"Q: {q}\nA: {a}" for q, a in answers.items()
            )
            return Message(
                content=content,
                sent_from="architect",
                cause_by="design_review_answered",
                send_to={"orchestrator"},
                metadata={
                    "artifact": "design_review_answers",
                    "answers": answers,
                    "assumed": True,
                    "ticket_id": ticket_id,
                    "ticket_title": ticket_title,
                    "ticket_description": ticket_description,
                },
            )

        prompt = build_prompt(
            ticket_title,
            ticket_description,
            architecture_content,
        )

        raw = run_kimi(prompt, phase_name, timeout_seconds, agent_id="architect")
        if inspect.isawaitable(raw):
            output = await raw
        else:
            output = raw

        questions = parse_questions(output or "")
        if not questions:
            # No questions could be extracted; treat as no pending decisions.
            answers = self._assumed_answers(architecture_content)
            content = "No se detectaron preguntas explícitas; respuestas asumidas:\n\n" + "\n".join(
                f"Q: {q}\nA: {a}" for q, a in answers.items()
            )
            return Message(
                content=content,
                sent_from="architect",
                cause_by="design_review_answered",
                send_to={"orchestrator"},
                metadata={
                    "artifact": "design_review_answers",
                    "answers": answers,
                    "assumed": True,
                    "ticket_id": ticket_id,
                    "ticket_title": ticket_title,
                    "ticket_description": ticket_description,
                },
            )

        return Message(
            content=output or "",
            sent_from="architect",
            cause_by="design_review_requested",
            send_to={"orchestrator"},
            metadata={
                "artifact": "design_review_questions",
                "questions": questions,
                "ticket_id": ticket_id,
                "ticket_title": ticket_title,
                "ticket_description": ticket_description,
            },
        )

    def _build_default_prompt(
        self,
        title: str,
        description: str,
        architecture_content: str,
    ) -> str:
        return (
            "Eres el Arquitecto de AgentFlow. Revisa el documento de arquitectura "
            "generado para el siguiente ticket y extrae SOLO las decisiones de diseño "
            "que aún deben ser confirmadas por el usuario u otro stakeholder.\n\n"
            f"TICKET:\nTÍTULO: {title}\nDESCRIPCIÓN: {description}\n\n"
            f"DOCUMENTO DE ARQUITECTURA:\n{architecture_content}\n\n"
            "Responde con una lista numerada de preguntas claras y breves. "
            "Si no hay decisiones pendientes, responde exactamente: 'SIN_DECISIONES_PENDIENTES'. "
            "Responde en español."
        )

    def _parse_questions(self, output: str) -> List[str]:
        questions: List[str] = []
        if not output:
            return questions

        stripped = output.strip()
        if "SIN_DECISIONES_PENDIENTES" in stripped:
            return questions

        marker = "DECISIONES PENDIENTES:"
        idx = stripped.find(marker)
        if idx != -1:
            block = stripped[idx + len(marker) :]
        else:
            block = stripped

        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("sin decisiones"):
                continue
            # Strip common list prefixes and numbering.
            if line[0].isdigit() and "." in line[:3]:
                line = line.split(".", 1)[1].strip()
            elif line.startswith(("-", "*")):
                line = line[1:].strip()
            if line:
                questions.append(line)

        return questions

    def _assumed_answers(self, architecture_content: str) -> Dict[str, str]:
        """Return conservative assumed answers when no external review is available."""
        return {
            "¿Usar stack/patrones existentes?": "Sí; mantener el stack y patrones actuales.",
            "¿Priorizar simplicidad o escalabilidad?": "Simplicidad, con puntos de extensión documentados.",
            "¿Aceptar dependencias del PRD?": "Sí, asumir que los requisitos del PRD son correctos.",
        }

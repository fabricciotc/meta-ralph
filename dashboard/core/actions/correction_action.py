from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.actions.base import Action
from core.models import Message


def default_build_correction_prompt(
    task: Dict[str, Any],
    reason: str,
    suggested_fix: str,
    repo_path: Any,
    branch: Optional[str],
) -> str:
    """Build the default correction prompt for an engineer."""
    files = task.get("files_to_touch", []) or []
    files_str = ", ".join(str(f) for f in files) if files else "N/A"

    return (
        "Eres un Senior Engineer. Genera un prompt de corrección claro y accionable para que "
        "otro ingeniero arregle los problemas detectados por QA.\n\n"
        f"TAREA: {task.get('id', '')} - {task.get('title', '')}\n"
        f"DESCRIPCIÓN: {task.get('description', '')}\n"
        f"COMPLEJIDAD: {task.get('complexity', 'M')}\n"
        f"ARCHIVOS: {files_str}\n\n"
        f"REPO: {repo_path}\n"
        f"RAMA: {branch or 'N/A'}\n\n"
        f"MOTIVO DEL RECHAZO:\n{reason}\n\n"
        f"SUGERENCIA DE QA:\n{suggested_fix or '(ninguna proporcionada)'}\n\n"
        "El prompt de corrección debe:\n"
        "1. Resumir el problema en una oración.\n"
        "2. Listar los pasos concretos para corregirlo.\n"
        "3. Indicar cómo validar localmente antes de volver a solicitar revisión.\n\n"
        "Responde en español."
    )


def default_extract_correction_prompt(output: Optional[str]) -> str:
    """Return the correction prompt, falling back to a default message."""
    if output and output.strip():
        return output.strip()
    return (
        "Corregir los problemas señalados por QA y volver a solicitar revisión. "
        "Verificar localmente build/tests antes de enviar."
    )


class CorrectionAction(Action):
    """Generates a correction prompt from a QA rejection."""

    async def run(
        self,
        context: List[Message],
        run_kimi: Optional[Any] = None,
        **kwargs,
    ) -> Message:
        required_keys = [
            "task",
            "task_id",
            "reason",
            "suggested_fix",
            "repo_path",
            "build_correction_prompt",
            "extract_correction_prompt",
            "phase_name",
            "timeout_seconds",
        ]
        missing = [key for key in required_keys if key not in kwargs]
        if missing:
            raise ValueError(f"CorrectionAction missing required kwargs: {missing}")

        task: Dict[str, Any] = kwargs["task"]
        task_id: str = kwargs["task_id"]
        reason: str = kwargs["reason"]
        suggested_fix: str = kwargs["suggested_fix"]
        repo_path: Any = kwargs["repo_path"]
        build_correction_prompt: Callable[..., str] = kwargs["build_correction_prompt"]
        extract_correction_prompt: Callable[..., str] = kwargs["extract_correction_prompt"]
        phase_name: str = kwargs["phase_name"]
        timeout_seconds: int = kwargs["timeout_seconds"]

        branch: Optional[str] = kwargs.get("branch")

        prompt = build_correction_prompt(
            task=task,
            reason=reason,
            suggested_fix=suggested_fix,
            repo_path=repo_path,
            branch=branch,
        )

        if run_kimi is None:
            content = extract_correction_prompt("")
        else:
            raw = run_kimi(
                prompt,
                phase_name,
                timeout_seconds,
                agent_id=f"qa-{task_id}",
            )
            if inspect.isawaitable(raw):
                output = await raw
            else:
                output = raw
            content = extract_correction_prompt(output)

        return Message(
            content=content,
            sent_from=f"qa-{task_id}",
            cause_by="correction_prompt_ready",
            send_to={"orchestrator"},
            metadata={
                "task_id": task_id,
                "task": task,
                "reason": reason,
                "suggested_fix": suggested_fix,
            },
        )

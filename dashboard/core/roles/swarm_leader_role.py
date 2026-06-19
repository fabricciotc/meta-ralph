from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.ai_execution import invoke_ai
from core.models import Message
from core.roles.team_leader_role import TeamLeaderRole


class SwarmLeaderRole(TeamLeaderRole):
    """Decomposes large tasks into parallel subtasks (Kimi Agent Swarm pattern).

    The swarm leader receives a ``decompose_request`` message describing a large
    task, uses the configured AI backend to split it into independent subtasks,
    and publishes a ``swarm_subtasks`` message with the decomposition.
    """

    role_id = "swarm-leader"
    _watch = ["decompose_request"]

    def __init__(
        self,
        run_ai: Optional[Any] = None,
        max_workers: int = 4,
        phase_name: str = "swarm-leader",
        timeout_seconds: int = 300,
    ):
        super().__init__(
            role_id=self.role_id,
            profile="Swarm Leader",
            run_ai=run_ai,
            max_retries=1,
            phase_name=phase_name,
            timeout_seconds=timeout_seconds,
        )
        self.max_workers = max(1, max_workers)

    async def run(self, env: Any, **kwargs) -> Optional[Message]:
        history = env.history() if hasattr(env, "history") else []
        queue = env.get_messages_for(self.role_id) if hasattr(env, "get_messages_for") else []
        context = self.observe(history + queue)
        trigger = self._find_trigger(context)
        if not trigger:
            return None
        self._mark_trigger_processed(trigger)

        if trigger.cause_by != "decompose_request":
            return None

        task_id = trigger.metadata.get("task_id", "unknown")
        title = trigger.metadata.get("title", task_id)
        description = trigger.metadata.get("description", trigger.content)
        complexity = trigger.metadata.get("complexity", "L")

        subtasks = await self._decompose(task_id, title, description, complexity)

        msg = Message(
            content=f"Decomposed {task_id} into {len(subtasks)} parallel subtasks.",
            sent_from=self.role_id,
            cause_by="swarm_subtasks",
            msg_type="swarm_subtasks",
            send_to={trigger.sent_from, "all"},
            metadata={
                "parent_task_id": task_id,
                "subtasks": subtasks,
            },
        )
        env.publish_message(msg)
        return msg

    async def _decompose(self, task_id: str, title: str, description: str, complexity: str) -> List[Dict[str, Any]]:
        if self.run_ai is not None:
            prompt = self._build_decompose_prompt(task_id, title, description, complexity)
            try:
                raw = await invoke_ai(self.run_ai, prompt, self.phase_name, self.timeout_seconds, self.role_id)
                if raw:
                    parsed = self._parse_subtasks(raw)
                    if parsed:
                        return self._normalize_subtasks(task_id, parsed)
            except Exception:
                pass
        return self._fallback_subtasks(task_id, title, description)

    def _build_decompose_prompt(self, task_id: str, title: str, description: str, complexity: str) -> str:
        return (
            "You are a Swarm Leader in a multi-agent coding system. "
            "A large task needs to be split into independent subtasks that can be implemented in parallel.\n\n"
            f"TASK ID: {task_id}\n"
            f"TITLE: {title}\n"
            f"DESCRIPTION: {description}\n"
            f"COMPLEXITY: {complexity}\n"
            f"MAX PARALLEL SUBTASKS: {self.max_workers}\n\n"
            "Respond EXACTLY with JSON in this shape:\n"
            '{\n'
            '  "subtasks": [\n'
            '    {"id": "T1a", "title": "Subtask title", "description": "what to do", "dependencies": []},\n'
            '    {"id": "T1b", "title": "...", "description": "...", "dependencies": ["T1a"]}\n'
            '  ]\n'
            '}\n'
            "Each subtask should be independent enough to run in parallel when dependencies allow."
        )

    def _parse_subtasks(self, raw: str) -> List[Dict[str, Any]]:
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
            return list(data.get("subtasks", []))
        except Exception:
            return []

    def _normalize_subtasks(
        self,
        parent_task_id: str,
        subtasks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized = []
        for i, st in enumerate(subtasks[: self.max_workers]):
            st = dict(st)
            st.setdefault("id", f"{parent_task_id}-{i + 1}")
            st.setdefault("title", f"Subtask {i + 1}")
            st.setdefault("description", "")
            st.setdefault("dependencies", [])
            st["parent_task_id"] = parent_task_id
            st.setdefault("complexity", "M")
            normalized.append(st)
        return normalized

    def _fallback_subtasks(self, task_id: str, title: str, description: str) -> List[Dict[str, Any]]:
        """Simple fallback decomposition when no AI backend is available."""
        return [
            {
                "id": f"{task_id}-1",
                "title": f"{title} - foundation",
                "description": f"Set up the foundation for: {description}",
                "dependencies": [],
                "parent_task_id": task_id,
                "complexity": "M",
            },
            {
                "id": f"{task_id}-2",
                "title": f"{title} - implementation",
                "description": f"Implement the core behavior for: {description}",
                "dependencies": [f"{task_id}-1"],
                "parent_task_id": task_id,
                "complexity": "M",
            },
        ]

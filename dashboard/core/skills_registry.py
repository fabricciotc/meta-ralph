from __future__ import annotations

from pathlib import Path
from typing import Dict, List

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
                lines.append(f"Activate the '{skill}' skill and apply its conventions and best practices.")
        elif prefix:
            lines.append(prefix.strip())
        return "\n".join(lines)

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


class CopilotCliBackend:
    name = "copilot"
    supports_skill_activation = True

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable

    def is_available(self) -> bool:
        if self.executable:
            return True
        self.executable = shutil.which("copilot") or shutil.which("gh")
        return self.executable is not None

    def _strip_ansi(self, text: str) -> str:
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def _build_command(self, prompt: str) -> List[str]:
        command: List[str] = [self.executable]
        if os.path.basename(self.executable) == "gh":
            command.append("copilot")
        command.append("-p")
        command.append(prompt)

        allow_tools = os.environ.get("AGENTICFLOW_COPILOT_ALLOW_TOOLS") or os.environ.get("META_RALPH_COPILOT_ALLOW_TOOLS")
        if allow_tools:
            for tool in allow_tools.split(","):
                tool = tool.strip()
                if tool:
                    command.append("--allow-tool")
                    command.append(tool)

        return command

    def run_prompt(
        self,
        prompt: str,
        *,
        phase_name: str,
        timeout_seconds: int,
        agent_id: Optional[str] = None,
        system_instructions: Optional[str] = None,
    ) -> Optional[str]:
        if not self.executable and not self.is_available():
            return None
        full_prompt = prompt
        if system_instructions:
            full_prompt = f"{system_instructions}\n\n{full_prompt}"
        try:
            proc = subprocess.run(
                self._build_command(full_prompt),
                cwd=str(Path.cwd()),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            output = proc.stdout or ""
            if proc.stderr:
                output += "\n" + proc.stderr
            lines = [self._strip_ansi(l) for l in output.splitlines() if self._strip_ansi(l).strip()]
            return "\n".join(lines)
        except Exception:
            return None

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
        if not self.executable and not self.is_available():
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

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
        if not self.executable and not self.is_available():
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
        except Exception:
            return None

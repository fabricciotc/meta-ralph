from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


class _FakeBackend:
    name = "fake"
    supports_skill_activation = False

    def is_available(self):
        return True

    def run_prompt(self, prompt, *, phase_name, timeout_seconds, agent_id=None, system_instructions=None):
        return f"output for {agent_id}"


class TestServerRunAiPrompt(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = Path.cwd()

    def tearDown(self):
        import os
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_files_are_isolated_by_agent_id(self):
        import os
        os.chdir(self.tmpdir)
        (Path(self.tmpdir) / ".agenticflow" / "state").mkdir(parents=True)

        ticket = {"id": "ISO-001", "title": "X", "description": "Y", "repoPath": str(self.tmpdir)}
        runner = server.AgentRunner(ticket)

        class FakeRegistry:
            def available_backends(self):
                return [_FakeBackend()]

            def run_prompt(self, prompt, *, phase_name, timeout_seconds, agent_id=None, system_instructions=None):
                return f"output for {agent_id}"

        runner.backend_registry = FakeRegistry()

        out1 = runner._run_ai_prompt("prompt1", phase_name="qa_review", timeout_seconds=10, agent_id="qa-T1")
        out2 = runner._run_ai_prompt("prompt2", phase_name="qa_review", timeout_seconds=10, agent_id="qa-T2")

        self.assertEqual(out1, "output for qa-T1")
        self.assertEqual(out2, "output for qa-T2")

        state_dir = server.get_meta_dir() / "state"
        outputs = sorted(state_dir.glob("output-ISO-001-qa_review-*.txt"))
        self.assertEqual(len(outputs), 2)
        self.assertTrue(any("qa-t1" in p.name for p in outputs))
        self.assertTrue(any("qa-t2" in p.name for p in outputs))


if __name__ == "__main__":
    unittest.main()

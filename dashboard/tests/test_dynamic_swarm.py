from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.dynamic_swarm import (
    DynamicSwarmDetector,
    DynamicSwarmExecutor,
    DynamicSwarmSynthesizer,
)
from core.orchestrator import Orchestrator
from core.skills_registry import SkillsRegistry


class TestSkillsRegistryHasRole(unittest.TestCase):
    def test_has_role_returns_true_for_known_role(self):
        registry = SkillsRegistry.__new__(SkillsRegistry)
        registry._data = {"security_specialist": {"skills": ["code-review"]}}
        self.assertTrue(registry.has_role("security_specialist"))

    def test_has_role_returns_false_for_unknown_role(self):
        registry = SkillsRegistry.__new__(SkillsRegistry)
        registry._data = {"security_specialist": {"skills": ["code-review"]}}
        self.assertFalse(registry.has_role("unknown_role"))


class TestDynamicSwarmDetector(unittest.TestCase):
    def test_keyword_detect_finds_security_specialist(self):
        detector = DynamicSwarmDetector()
        roles = asyncio.run(detector.detect(
            {"title": "Add OAuth", "description": "Implement OAuth2 login"},
            "We need secure authentication.",
        ))
        self.assertIn("security_specialist", roles)

    def test_keyword_detect_finds_performance_specialist(self):
        detector = DynamicSwarmDetector()
        roles = asyncio.run(detector.detect(
            {"title": "Optimize", "description": "Reduce latency"},
            "The endpoint is slow and needs caching.",
        ))
        self.assertIn("performance_specialist", roles)

    def test_ai_detect_returns_valid_roles(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return '{"specialists": ["accessibility_specialist", "invalid_role"]}'

        detector = DynamicSwarmDetector(run_ai=mock_run_ai)
        roles = asyncio.run(detector.detect(
            {"title": "UI", "description": "Build a form"},
            "No keyword hits here.",
        ))
        self.assertIn("accessibility_specialist", roles)
        self.assertNotIn("invalid_role", roles)

    def test_detect_deduplicates_and_preserves_order(self):
        def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
            return '{"specialists": ["security_specialist"]}'

        detector = DynamicSwarmDetector(run_ai=mock_run_ai)
        roles = asyncio.run(detector.detect(
            {"title": "Auth", "description": "OAuth and JWT"},
            "security context",
        ))
        self.assertEqual(roles.count("security_specialist"), 1)
        self.assertEqual(roles[0], "security_specialist")


class TestDynamicSwarmExecutor(unittest.TestCase):
    def test_executor_writes_specialist_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            class FakeContext:
                prd_path = output_dir / "prd.md"
                architecture_path = output_dir / "arch.md"
                tasks_path = output_dir / "tasks.json"
                design_path = output_dir / "design.md"

                def log(self, message, level="info"):
                    pass

            FakeContext.prd_path.write_text("# PRD\n\nBuild a login form.", encoding="utf-8")

            async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
                return f"# {agent_id} findings\n\nKey finding."

            executor = DynamicSwarmExecutor(run_ai=mock_run_ai, max_workers=2)
            files = asyncio.run(executor.run(
                ticket={"id": "TKT-1", "title": "Login", "description": "OAuth"},
                role_ids=["security_specialist"],
                context=FakeContext(),
                output_dir=output_dir,
            ))

            self.assertIn("security_specialist", files)
            self.assertTrue(files["security_specialist"].exists())
            content = files["security_specialist"].read_text(encoding="utf-8")
            self.assertIn("Key finding", content)


class TestDynamicSwarmSynthesizer(unittest.TestCase):
    def test_synthesizer_writes_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = {
                "security_specialist": Path(tmpdir) / "TKT-1-security_specialist.md",
            }
            files["security_specialist"].write_text("# Security findings", encoding="utf-8")
            output_path = Path(tmpdir) / "report.md"

            async def mock_run_ai(prompt, phase_name, timeout_seconds, agent_id=None):
                return "# Synthesized report"

            synthesizer = DynamicSwarmSynthesizer(run_ai=mock_run_ai)
            result = asyncio.run(synthesizer.synthesize(
                ticket={"id": "TKT-1", "title": "Login", "description": "OAuth"},
                files=files,
                output_path=output_path,
            ))

            self.assertIn("Synthesized report", result)
            self.assertTrue(output_path.exists())


class TestOrchestratorSwarmPhase(unittest.TestCase):
    def test_build_swarm_context_text_includes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = Orchestrator(
                ticket={"id": "TKT-SWARM", "title": "Test", "description": "Desc"},
                callbacks={},
            )
            orchestrator._meta_dir = lambda: Path(tmpdir)

            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "prd-TKT-SWARM.md").write_text("# PRD", encoding="utf-8")
            (state_dir / "architecture-TKT-SWARM.md").write_text("# Arch", encoding="utf-8")

            text = orchestrator._build_swarm_context_text()
            self.assertIn("# PRD", text)
            self.assertIn("# Arch", text)


if __name__ == "__main__":
    unittest.main()

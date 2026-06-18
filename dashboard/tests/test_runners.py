from unittest.mock import patch

from core.runners.registry import BackendRegistry


class FakeBackend:
    name = "fake"
    supports_skill_activation = False

    def __init__(self, available=True, output="ok"):
        self._available = available
        self._output = output

    def is_available(self):
        return self._available

    def run_prompt(self, prompt, *, phase_name, timeout_seconds, agent_id=None, system_instructions=None):
        return self._output


def test_registry_picks_first_available():
    registry = BackendRegistry([FakeBackend(available=False), FakeBackend(available=True, output="hello")])
    assert registry.run_prompt("hi", phase_name="test", timeout_seconds=10) == "hello"


def test_registry_fallback_on_none():
    class FailingBackend(FakeBackend):
        name = "failing"

        def run_prompt(self, prompt, *, phase_name, timeout_seconds, agent_id=None, system_instructions=None):
            return None

    registry = BackendRegistry([FailingBackend(available=True), FakeBackend(available=True, output="fallback")])
    assert registry.run_prompt("hi", phase_name="test", timeout_seconds=10) == "fallback"


def test_kimi_backend_detects_executable():
    with patch("core.runners.kimi_cli.shutil.which", return_value="/usr/bin/kimi"):
        from core.runners.kimi_cli import KimiCliBackend
        assert KimiCliBackend().is_available() is True


def test_kimi_backend_runs_prompt(monkeypatch):
    with patch("core.runners.kimi_cli.shutil.which", return_value="/usr/bin/kimi"):
        from core.runners.kimi_cli import KimiCliBackend
        backend = KimiCliBackend()
        called = {}

        def fake_run(*args, **kwargs):
            called["args"] = args
            called["kwargs"] = kwargs
            class R:
                stdout = "kimi output"
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        output = backend.run_prompt("hello", phase_name="test", timeout_seconds=10, agent_id="a1")
        assert output == "kimi output"
        assert called["args"][0][0] == "/usr/bin/kimi"


def test_cursor_backend_uses_cli():
    with patch("core.runners.cursor_cli.shutil.which", return_value="/usr/bin/cursor"):
        from core.runners.cursor_cli import CursorCliBackend
        backend = CursorCliBackend()
        assert backend.is_available() is True
        with patch("subprocess.run", return_value=type("R", (), {"stdout": "cursor out", "stderr": "", "returncode": 0})) as mock_run:
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "cursor out"
            assert mock_run.call_args[0][0] == [
                "/usr/bin/cursor",
                "-p",
                "--trust",
                "--force",
                "--",
                "hi",
            ]


def test_claude_backend_uses_cli():
    with patch("core.runners.claude_code.shutil.which", return_value="/usr/bin/claude"):
        from core.runners.claude_code import ClaudeCodeBackend
        backend = ClaudeCodeBackend()
        assert backend.is_available() is True
        with patch("subprocess.run", return_value=type("R", (), {"stdout": "claude out", "stderr": "", "returncode": 0})) as mock_run:
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "claude out"
            assert mock_run.call_args[0][0][0] == "/usr/bin/claude"


def test_codex_backend_uses_cli():
    with patch("core.runners.codex_cli.shutil.which", return_value="/usr/bin/codex"):
        from core.runners.codex_cli import CodexCliBackend
        backend = CodexCliBackend()
        assert backend.is_available() is True
        with patch("subprocess.run", return_value=type("R", (), {"stdout": "codex out", "stderr": "", "returncode": 0})) as mock_run:
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "codex out"
            assert mock_run.call_args[0][0][0] == "/usr/bin/codex"


def test_openai_api_backend_requires_key():
    with patch.dict("os.environ", {}, clear=True):
        from core.runners.openai_api import OpenAIApiBackend
        backend = OpenAIApiBackend()
        assert backend.is_available() is False


def test_openai_api_backend_calls_endpoint():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False):
        from core.runners.openai_api import OpenAIApiBackend
        backend = OpenAIApiBackend(model="gpt-4o-mini")
        assert backend.is_available() is True
        with patch("requests.post") as mock_post:
            mock_post.return_value = type(
                "R",
                (),
                {
                    "status_code": 200,
                    "json": lambda: {"choices": [{"message": {"content": "api output"}}]},
                    "raise_for_status": lambda: None,
                },
            )
            out = backend.run_prompt("hi", phase_name="p", timeout_seconds=5)
            assert out == "api output"

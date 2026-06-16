import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "/Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard")

import server


def _stub_run(self):
    """Stub AgentRunner.run that marks the run as completed quickly."""
    with server.run_lock:
        state = server.load_run_state()
        state.update({
            "active": True,
            "ticketId": self.ticket_id,
            "status": "in-design",
            "currentAgent": "orchestrator",
            "progress": 5,
            "startedAt": server.datetime.now(server.timezone.utc).isoformat(),
            "logs": [],
            "agents": [],
            "messages": [],
            "communication": server._default_communication(),
            "designReview": None,
        })
        server.save_run_state(state)
    server.update_ticket_status(self.ticket_id, "in-design")
    server.update_ticket_runtime(
        self.ticket_id,
        startedAt=server.datetime.now(server.timezone.utc).isoformat(),
        elapsedSeconds=0,
        summary="Simulando ejecución...",
    )
    server.update_ticket_status(self.ticket_id, "done")
    with server.run_lock:
        state = server.load_run_state()
        if state.get("ticketId") == self.ticket_id:
            state["active"] = False
            state["status"] = "completed"
            state["progress"] = 100
            server.save_run_state(state)


def test_restart_ticket_clears_state_and_artifacts():
    tmpdir = Path(tempfile.mkdtemp(prefix="meta-ralph-restart-test-"))
    try:
        board_path = tmpdir / "board.json"
        board = {
            "columns": server.DEFAULT_COLUMNS.copy(),
            "tickets": [
                {
                    "id": "TKT-RESTART",
                    "title": "Ticket restart",
                    "status": "done",
                    "repoPath": "/tmp/fake-repo",
                    "branch": "",
                    "assigneeRole": "backend",
                    "featureFocus": "focus",
                    "labels": [],
                    "blocked": False,
                    "createdAt": server.datetime.now(server.timezone.utc).isoformat(),
                    "updatedAt": server.datetime.now(server.timezone.utc).isoformat(),
                }
            ],
            "stats": {"total": 1, "done": 1, "inProgress": 0, "blocked": 0},
            "lastUpdated": server.datetime.now(server.timezone.utc).isoformat(),
        }
        board_path.write_text(json.dumps(board), encoding="utf-8")
        server.set_board_path(str(board_path))
        server.RUN_STATE_FILE = tmpdir / "run-state.json"
        server.LOG_FILE = tmpdir / "run.log"

        # Isolate generated artifacts to a temp meta dir.
        meta_dir = tmpdir / "meta"
        state_dir = meta_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        original_get_meta_dir = server.get_meta_dir
        server.get_meta_dir = lambda: meta_dir

        try:
            # Create artifacts.
            (state_dir / f"prd-TKT-RESTART.md").write_text("PRD", encoding="utf-8")
            (state_dir / f"tasks-TKT-RESTART.json").write_text("[]", encoding="utf-8")
            (state_dir / f"architecture-TKT-RESTART.md").write_text("ARCH", encoding="utf-8")
            snapshot_path = server.get_ticket_snapshot_path("TKT-RESTART")
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text("{}", encoding="utf-8")

            with patch.object(server.AgentRunner, "run", _stub_run):
                ok, msg = server.restart_ticket("TKT-RESTART")
                assert ok, msg

            # Artifacts should be gone.
            assert not (state_dir / "prd-TKT-RESTART.md").exists()
            assert not (state_dir / "tasks-TKT-RESTART.json").exists()
            assert not (state_dir / "architecture-TKT-RESTART.md").exists()
            assert not snapshot_path.exists()

            # Ticket should be back to ready-for-work.
            ticket = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-RESTART")
            assert ticket["status"] == "ready-for-work"

            # Wait for the stub thread to complete the new run.
            for _ in range(100):
                state = server.load_run_state()
                if state.get("status") == "completed":
                    break
                time.sleep(0.05)
            state = server.load_run_state()
            assert state.get("status") == "completed"
            assert state.get("ticketId") == "TKT-RESTART"
        finally:
            server.get_meta_dir = original_get_meta_dir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_restart_ticket_not_found():
    ok, msg = server.restart_ticket("TKT-NONEXISTENT")
    assert not ok
    assert "no encontrado" in msg.lower()

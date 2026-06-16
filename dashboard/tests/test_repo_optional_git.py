import sys
import time
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


def fast_run(self):
    """Simulate an AgentRunner that completes the ticket quickly."""
    def wait_or_stop(seconds):
        for _ in range(int(seconds * 10)):
            if self._stop_event.is_set():
                return False
            time.sleep(0.1)
        return True

    try:
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
            summary="Simulating execution...",
        )
        if not wait_or_stop(0.3):
            return
        server.update_ticket_status(self.ticket_id, "in-progress")
        if not wait_or_stop(0.3):
            return
        server.update_ticket_status(self.ticket_id, "in-review")
        if not wait_or_stop(0.3):
            return
        server.update_ticket_status(self.ticket_id, "done")
        with server.run_lock:
            state = server.load_run_state()
            if state.get("ticketId") == self.ticket_id:
                state["active"] = False
                state["status"] = "completed"
                state["progress"] = 100
                server.save_run_state(state)
    except Exception as exc:
        print(f"Error in fast_run: {exc}")
        with server.run_lock:
            state = server.load_run_state()
            if state.get("ticketId") == self.ticket_id:
                state["active"] = False
                server.save_run_state(state)
    finally:
        if not self._stop_event.is_set():
            time.sleep(0.2)
            server.process_next_in_queue()


def wait_for(condition, timeout=10, interval=0.2):
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return True
        time.sleep(interval)
    return False


def main():
    tmpdir = Path(tempfile.mkdtemp(prefix="agentflow-test-no-git-"))
    print(f"Test directory: {tmpdir}")
    no_git_repo = tmpdir / "repo-without-git"
    no_git_repo.mkdir()
    try:
        board_path = tmpdir / "board.json"
        board = {
            "columns": server.DEFAULT_COLUMNS.copy(),
            "tickets": [
                {
                    "id": "TKT-NOGIT",
                    "title": "Ticket without git",
                    "status": "backlog",
                    "repoPath": str(no_git_repo),
                    "branch": "",
                    "assigneeRole": "backend",
                    "featureFocus": "focus",
                    "labels": [],
                    "blocked": False,
                    "createdAt": server.datetime.now(server.timezone.utc).isoformat(),
                    "updatedAt": server.datetime.now(server.timezone.utc).isoformat(),
                }
            ],
            "stats": {"total": 1, "done": 0, "inProgress": 0, "blocked": 0},
            "lastUpdated": server.datetime.now(server.timezone.utc).isoformat(),
        }
        board_path.write_text(json.dumps(board), encoding="utf-8")
        server.set_board_path(str(board_path))
        server.RUN_STATE_FILE = tmpdir / "run-state.json"
        server.LOG_FILE = tmpdir / "run.log"

        print(f"Repo without git: {no_git_repo}")
        assert not (no_git_repo / ".git").exists(), "The test repo should not have .git"

        with patch.object(server.AgentRunner, "run", fast_run):
            ticket = server.load_board()["tickets"][0]
            ticket["status"] = "ready-for-work"
            server.save_board(server.load_board())

            print("Moving ticket to ready-for-work (without git)...")
            err_code, err_msg = server.validate_git_repo(ticket["repoPath"])
            assert err_code is None, f"validate_git_repo failed: {err_code} - {err_msg}"

            branch, err_code, err_msg = server.create_git_branch(
                ticket["repoPath"], ticket["id"], ticket["title"]
            )
            assert err_code is None, f"create_git_branch failed: {err_code} - {err_msg}"
            assert branch == "", f"Without git the branch should be empty, got: {branch}"

            ticket["branch"] = branch
            ticket["repoPath"] = server.resolve_repo_path(ticket["repoPath"])
            server.save_board(server.load_board())

            print("Starting automatic execution...")
            server.start_automatic_run(ticket)

            ok = wait_for(
                lambda: next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-NOGIT")["status"] == "done",
                timeout=15,
            )
            assert ok, "The ticket did not finish without git"

            final_ticket = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-NOGIT")
            print(f"OK: Ticket without git finished: status={final_ticket['status']}, branch='{final_ticket.get('branch')}'")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()

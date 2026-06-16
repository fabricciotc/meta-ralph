import sys
import time
import json
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

# Ensure the dashboard is on the path.
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
        # Simulate work.
        if not wait_or_stop(0.3):
            print(f"fast_run {self.ticket_id}: stopped during in-design")
            return
        if self._should_stop():
            print(f"fast_run {self.ticket_id}: stopped before in-progress")
            return
        server.update_ticket_status(self.ticket_id, "in-progress")
        if not wait_or_stop(0.3):
            print(f"fast_run {self.ticket_id}: stopped during in-progress")
            return
        if self._should_stop():
            print(f"fast_run {self.ticket_id}: stopped before in-review")
            return
        server.update_ticket_status(self.ticket_id, "in-review")
        if not wait_or_stop(0.3):
            print(f"fast_run {self.ticket_id}: stopped during in-review")
            return
        if self._should_stop():
            print(f"fast_run {self.ticket_id}: stopped before done")
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
        print(f"Error in fast_run for {self.ticket_id}: {exc}")
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
    tmpdir = Path(tempfile.mkdtemp(prefix="meta-ralph-test-"))
    print(f"Test directory: {tmpdir}")
    try:
        board_path = tmpdir / "board.json"
        board = {
            "columns": server.DEFAULT_COLUMNS.copy(),
            "tickets": [
                {
                    "id": "TKT-001",
                    "title": "Ticket one",
                    "status": "backlog",
                    "repoPath": "/tmp/fake-repo",
                    "branch": "",
                    "assigneeRole": "backend",
                    "featureFocus": "focus",
                    "labels": [],
                    "blocked": False,
                    "createdAt": server.datetime.now(server.timezone.utc).isoformat(),
                    "updatedAt": server.datetime.now(server.timezone.utc).isoformat(),
                },
                {
                    "id": "TKT-002",
                    "title": "Ticket two",
                    "status": "ready-for-work",
                    "repoPath": "/tmp/fake-repo",
                    "branch": "",
                    "assigneeRole": "backend",
                    "featureFocus": "focus",
                    "labels": [],
                    "blocked": False,
                    "createdAt": server.datetime.now(server.timezone.utc).isoformat(),
                    "updatedAt": server.datetime.now(server.timezone.utc).isoformat(),
                },
            ],
            "stats": {"total": 2, "done": 0, "inProgress": 0, "blocked": 0},
            "lastUpdated": server.datetime.now(server.timezone.utc).isoformat(),
        }
        board_path.write_text(json.dumps(board), encoding="utf-8")
        print("Configuring paths...")
        server.set_board_path(str(board_path))
        server.RUN_STATE_FILE = tmpdir / "run-state.json"
        server.LOG_FILE = tmpdir / "run.log"

        # Clean previous state.
        print("Loading run state...")
        state = server.load_run_state()
        print(f"Initial state: active={state.get('active')}, ticketId={state.get('ticketId')}, status={state.get('status')}")

        with patch.object(server.AgentRunner, "run", fast_run):
            # Simulate PATCH TKT-001 -> ready-for-work.
            print("Moving TKT-001 to ready-for-work...")
            ticket = server.load_board()["tickets"][0]
            ticket["status"] = "ready-for-work"
            server.save_board(server.load_board())
            print("Calling start_automatic_run...")
            server.start_automatic_run(ticket)
            print("start_automatic_run returned")

            # Wait for TKT-001 to finish and TKT-002 to start.
            def debug_state():
                state = server.load_run_state()
                board = server.load_board()
                print(f"  [debug] runState ticketId={state.get('ticketId')} active={state.get('active')} status={state.get('status')} queue={state.get('queue')}")
                print(f"  [debug] board TKT-001={board['tickets'][0]['status']} TKT-002={board['tickets'][1]['status']}")
                return state.get("ticketId") == "TKT-002"
            ok = wait_for(debug_state, timeout=5)
            assert ok, "TKT-002 did not start after TKT-001"
            print(f"OK: TKT-001 done; TKT-002 active: status={server.load_board()['tickets'][1]['status']}, runState={server.load_run_state().get('status')}")

            # Verify that TKT-001 is done.
            t1 = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-001")
            assert t1["status"] == "done", f"TKT-001 should be done, got {t1['status']}"

            # Wait for TKT-002 to reach in-progress.
            ok = wait_for(lambda: server.load_board()["tickets"][1]["status"] == "in-progress")
            assert ok, "TKT-002 did not reach in-progress"
            print("OK: TKT-002 in progress")

            # Simulate moving TKT-002 to backlog, like api_update_ticket would.
            print("Moving TKT-002 to backlog...")
            server.update_ticket_status("TKT-002", "backlog")

            # Simulate the stop portion of api_update_ticket.
            # api_update_ticket does not take run_lock before invoking stop_active_run
            # because stop_active_run handles it internally.
            print("Checking whether TKT-002 is active and stopping...")
            state = server.load_run_state()
            if state.get("ticketId") == "TKT-002" and state.get("active"):
                print("Calling stop_active_run...")
                server.stop_active_run("Ticket TKT-002 moved to backlog; stopping execution")
                print("stop_active_run returned")

            # Wait for run-state cleanup.
            print("Waiting for run-state cleanup...")
            ok = wait_for(lambda: server.load_run_state().get("ticketId") is None and not server.load_run_state().get("active"))
            assert ok, "run-state was not cleaned after backlog"
            state = server.load_run_state()
            print(f"OK: After backlog: active={state.get('active')}, ticketId={state.get('ticketId')}, agents={len(state.get('agents', []))}")

            # Verify that TKT-002 is in backlog.
            t2 = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-002")
            assert t2["status"] == "backlog"

            # Simulate moving TKT-002 back to ready-for-work; it should restart from zero.
            t2["status"] = "ready-for-work"
            # Reset metrics as api_update_ticket does.
            for field in ["startedAt", "elapsedSeconds", "totalSeconds", "finishedAt", "summary"]:
                t2.pop(field, None)
            t2["branch"] = ""
            server.save_board(server.load_board())

            # Call start_automatic_run.
            server.start_automatic_run(t2)

            # Wait for TKT-002 to become active again.
            ok = wait_for(lambda: server.load_run_state().get("ticketId") == "TKT-002")
            assert ok, "TKT-002 did not restart"
            t2 = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-002")
            print(f"OK: TKT-002 restarted: status={t2['status']}, startedAt={t2.get('startedAt')}, elapsed={t2.get('elapsedSeconds')}")

            # Wait for completion (reload board each time).
            ok = wait_for(
                lambda: next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-002")["status"] == "done",
                timeout=15,
            )
            assert ok, "TKT-002 did not finish after restart"
            print("OK: Full flow validated")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()

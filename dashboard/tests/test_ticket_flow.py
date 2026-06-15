import sys
import time
import json
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

# Asegurar que el dashboard esté en el path
sys.path.insert(0, "/Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard")

import server


def fast_run(self):
    """Simula un AgentRunner que completa el ticket rápidamente."""
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
            summary="Simulando ejecución...",
        )
        # Simular trabajo
        if not wait_or_stop(0.3):
            print(f"fast_run {self.ticket_id}: detenido durante in-design")
            return
        if self._should_stop():
            print(f"fast_run {self.ticket_id}: detenido antes de in-progress")
            return
        server.update_ticket_status(self.ticket_id, "in-progress")
        if not wait_or_stop(0.3):
            print(f"fast_run {self.ticket_id}: detenido durante in-progress")
            return
        if self._should_stop():
            print(f"fast_run {self.ticket_id}: detenido antes de in-review")
            return
        server.update_ticket_status(self.ticket_id, "in-review")
        if not wait_or_stop(0.3):
            print(f"fast_run {self.ticket_id}: detenido durante in-review")
            return
        if self._should_stop():
            print(f"fast_run {self.ticket_id}: detenido antes de done")
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
        print(f"Error en fast_run para {self.ticket_id}: {exc}")
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
    print(f"Directorio de prueba: {tmpdir}")
    try:
        board_path = tmpdir / "board.json"
        board = {
            "columns": server.DEFAULT_COLUMNS.copy(),
            "tickets": [
                {
                    "id": "TKT-001",
                    "title": "Ticket uno",
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
                    "title": "Ticket dos",
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
        print("Configurando paths...")
        server.set_board_path(str(board_path))
        server.RUN_STATE_FILE = tmpdir / "run-state.json"
        server.LOG_FILE = tmpdir / "run.log"

        # Limpiar estado previo
        print("Cargando run state...")
        state = server.load_run_state()
        print(f"Estado inicial: active={state.get('active')}, ticketId={state.get('ticketId')}, status={state.get('status')}")

        with patch.object(server.AgentRunner, "run", fast_run):
            # Simular PATCH TKT-001 -> ready-for-work
            print("Moviendo TKT-001 a ready-for-work...")
            ticket = server.load_board()["tickets"][0]
            ticket["status"] = "ready-for-work"
            server.save_board(server.load_board())
            print("Llamando start_automatic_run...")
            server.start_automatic_run(ticket)
            print("start_automatic_run retornó")

            # Esperar a que TKT-001 termine y TKT-002 empiece
            def debug_state():
                state = server.load_run_state()
                board = server.load_board()
                print(f"  [debug] runState ticketId={state.get('ticketId')} active={state.get('active')} status={state.get('status')} queue={state.get('queue')}")
                print(f"  [debug] board TKT-001={board['tickets'][0]['status']} TKT-002={board['tickets'][1]['status']}")
                return state.get("ticketId") == "TKT-002"
            ok = wait_for(debug_state, timeout=5)
            assert ok, "TKT-002 no inició después de TKT-001"
            print(f"✅ TKT-001 done; TKT-002 activo: status={server.load_board()['tickets'][1]['status']}, runState={server.load_run_state().get('status')}")

            # Verificar que TKT-001 está en done
            t1 = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-001")
            assert t1["status"] == "done", f"TKT-001 debería estar done, está {t1['status']}"

            # Esperar a que TKT-002 esté in-progress
            ok = wait_for(lambda: server.load_board()["tickets"][1]["status"] == "in-progress")
            assert ok, "TKT-002 no llegó a in-progress"
            print(f"✅ TKT-002 en progreso")

            # Simular mover TKT-002 a backlog (como haría api_update_ticket)
            print("Moviendo TKT-002 a backlog...")
            server.update_ticket_status("TKT-002", "backlog")

            # Simulamos la parte de detención de api_update_ticket.
            # api_update_ticket no toma run_lock antes de invocar stop_active_run
            # porque stop_active_run lo maneja internamente.
            print("Verificando si TKT-002 es activo y deteniendo...")
            state = server.load_run_state()
            if state.get("ticketId") == "TKT-002" and state.get("active"):
                print("Llamando stop_active_run...")
                server.stop_active_run("Ticket TKT-002 movido a backlog; deteniendo ejecución")
                print("stop_active_run retornó")

            # Esperar a que run-state se limpie
            print("Esperando limpieza de run-state...")
            ok = wait_for(lambda: server.load_run_state().get("ticketId") is None and not server.load_run_state().get("active"))
            assert ok, "run-state no se limpió tras backlog"
            state = server.load_run_state()
            print(f"✅ Tras backlog: active={state.get('active')}, ticketId={state.get('ticketId')}, agents={len(state.get('agents', []))}")

            # Verificar que TKT-002 está en backlog
            t2 = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-002")
            assert t2["status"] == "backlog"

            # Simular mover TKT-002 de vuelta a ready-for-work (debe reiniciar de 0)
            t2["status"] = "ready-for-work"
            # Reiniciar métricas como lo hace api_update_ticket
            for field in ["startedAt", "elapsedSeconds", "totalSeconds", "finishedAt", "summary"]:
                t2.pop(field, None)
            t2["branch"] = ""
            server.save_board(server.load_board())

            # Llamar start_automatic_run
            server.start_automatic_run(t2)

            # Esperar a que TKT-002 esté activo de nuevo
            ok = wait_for(lambda: server.load_run_state().get("ticketId") == "TKT-002")
            assert ok, "TKT-002 no reinició"
            t2 = next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-002")
            print(f"✅ TKT-002 reiniciado: status={t2['status']}, startedAt={t2.get('startedAt')}, elapsed={t2.get('elapsedSeconds')}")

            # Esperar a que termine (recargar board cada vez)
            ok = wait_for(
                lambda: next(t for t in server.load_board()["tickets"] if t["id"] == "TKT-002")["status"] == "done",
                timeout=15,
            )
            assert ok, "TKT-002 no terminó tras reinicio"
            print("✅ Flujo completo validado")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()

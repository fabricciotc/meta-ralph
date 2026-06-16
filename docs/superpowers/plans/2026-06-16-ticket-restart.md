> I'm using the writing-plans skill to create the implementation plan.

# Ticket Restart Implementation Plan

**Goal:** Add a full-restart control for a ticket that clears its run progress and generated artifacts, asks for confirmation, and re-runs the pipeline from scratch.

**Architecture:** A single backend helper `restart_ticket(ticket_id)` stops any active/paused runner, deletes the ticket's snapshots and generated artifacts, resets the run-state, moves the ticket back to `ready-for-work`, and calls `play_ticket`. The UI reuses the existing `confirm-modal` and adds a restart icon next to play/pause in the tickets list.

**Tech Stack:** Python Flask, vanilla JS, existing dashboard HTML/CSS.

---

## Task 1: Backend restart helper and endpoint

**Files:**
- Modify: `dashboard/server.py`
- Test: `dashboard/tests/test_ticket_restart.py`

### Step 1.1: Add `restart_ticket` helper

Insert near `play_ticket`/`pause_active_ticket` (around line 2885):

```python
def restart_ticket(ticket_id):
    """Restart a ticket from scratch: stop runner, delete artifacts and run-state, then re-run."""
    global _active_run_thread

    board = load_board()
    ticket = next((t for t in board.get("tickets", []) if t.get("id") == ticket_id), None)
    if not ticket:
        return False, "Ticket no encontrado"

    # Stop active runner for this ticket.
    if _active_run_thread and _active_run_thread.is_alive() and _active_run_thread.ticket_id == ticket_id:
        _active_run_thread.stop()
        _active_run_thread.join(timeout=3)
        _active_run_thread = None

    # Remove any paused thread for this ticket.
    paused_run_threads.pop(ticket_id, None)

    # Delete snapshot on disk.
    delete_ticket_snapshot(ticket_id)

    # Delete generated artifacts.
    state_dir = get_meta_dir() / "state"
    if state_dir.exists():
        for pattern in [
            f"prd-{ticket_id}.md",
            f"tasks-{ticket_id}.json",
            f"architecture-{ticket_id}.md",
            f"design-review-{ticket_id}.*",
        ]:
            for path in state_dir.glob(pattern):
                try:
                    path.unlink()
                except OSError:
                    pass

    # Reset global run-state to idle.
    reset_run_state_to_idle()

    # Move ticket back to ready-for-work.
    update_ticket_status(ticket_id, "ready-for-work")

    # Start from scratch.
    ok, msg = play_ticket(ticket_id)
    if ok:
        return True, f"Ticket {ticket_id} reiniciado desde cero"
    return False, f"No se pudo reiniciar el ticket: {msg}"
```

### Step 1.2: Add endpoint

Insert after `api_play_ticket` (around line 3141):

```python
@app.route("/api/tickets/<ticket_id>/restart", methods=["POST"])
def api_restart_ticket(ticket_id):
    ok, msg = restart_ticket(ticket_id)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)
```

### Step 1.3: Run backend syntax check

```bash
cd dashboard
python -m py_compile server.py
```

---

## Task 2: Frontend restart button and confirmation

**Files:**
- Modify: `dashboard/static/app.js`
- Modify: `dashboard/static/style.css` (optional styling)

### Step 2.1: Render restart button

In `renderTicketsList` around the `runAction` template (line ~783), change:

```javascript
    const runAction = runStatus === 'running'
      ? `<button type="button" class="btn-icon btn-small ticket-action-pause" data-id="${escapeHtml(ticket.id)}" title="Pausar"><i data-lucide="pause"></i></button>`
      : isRunnable
        ? `<button type="button" class="btn-icon btn-small ticket-action-play" data-id="${escapeHtml(ticket.id)}" title="${runStatus === 'paused' ? 'Reanudar' : 'Ejecutar'}"><i data-lucide="play"></i></button>`
        : '';
```

to:

```javascript
    const showRestart = ['ready-for-work', 'in-design', 'in-progress', 'in-review', 'done'].includes(ticket.status);
    const runAction = runStatus === 'running'
      ? `<button type="button" class="btn-icon btn-small ticket-action-pause" data-id="${escapeHtml(ticket.id)}" title="Pausar"><i data-lucide="pause"></i></button>`
      : isRunnable
        ? `<button type="button" class="btn-icon btn-small ticket-action-play" data-id="${escapeHtml(ticket.id)}" title="${runStatus === 'paused' ? 'Reanudar' : 'Ejecutar'}"><i data-lucide="play"></i></button>`
        : '';
    const restartAction = showRestart
      ? `<button type="button" class="btn-icon btn-small ticket-action-restart" data-id="${escapeHtml(ticket.id)}" title="Reiniciar desde cero"><i data-lucide="refresh-cw"></i></button>`
      : '';
```

Then include `${restartAction}` in the row HTML next to `${runAction}`.

### Step 2.2: Bind restart click

After play/pause bindings (around line 812):

```javascript
    const restartBtn = row.querySelector('.ticket-action-restart');
    if (restartBtn) restartBtn.addEventListener('click', (e) => { e.stopPropagation(); restartTicket(ticket.id); });
```

### Step 2.3: Add `restartTicket` handler

Insert near `playTicket`/`pauseTicket`:

```javascript
async function restartTicket(ticketId) {
  const confirmed = await showConfirmModal({
    title: 'Reiniciar ticket',
    message: `¿Reiniciar el ticket ${ticketId} desde cero?\n\nSe borrarán el progreso del run, snapshots y los artefactos generados (PRD, plan de tareas, arquitectura). Los cambios de código en el repositorio no se eliminarán.`,
    okText: 'Reiniciar',
    cancelText: 'Cancelar',
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/tickets/${ticketId}/restart`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Error');
    showToast(data.message || 'Ticket reiniciado');
  } catch (err) {
    showToast('Error reiniciando ticket: ' + err.message, 'error');
  }
}
```

---

## Task 3: Optional restart button styling

**Files:**
- Modify: `dashboard/static/style.css`

Add near the ticket action button styles:

```css
.ticket-action-restart {
  color: var(--error, #ef4444);
}
.ticket-action-restart:hover {
  background: rgba(239, 68, 68, 0.1);
}
```

If `--error` variable does not exist, use a fallback red.

---

## Task 4: Tests

**Files:**
- Create: `dashboard/tests/test_ticket_restart.py`

### Step 4.1: Write test

```python
import sys
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "/Users/fabricciotornero/.kimi-code/skills/meta-ralph/dashboard")

import server


def fast_run(self):
    """Stub AgentRunner.run that completes immediately."""
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

        # Create artifacts.
        state_dir = server.get_meta_dir() / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "prd-TKT-RESTART.md").write_text("PRD", encoding="utf-8")
        (state_dir / "tasks-TKT-RESTART.json").write_text("[]", encoding="utf-8")
        (state_dir / "architecture-TKT-RESTART.md").write_text("ARCH", encoding="utf-8")
        (server.get_ticket_snapshot_path("TKT-RESTART")).write_text("{}", encoding="utf-8")

        # Mock runner to avoid real execution.
        with patch.object(server.AgentRunner, "run", fast_run):
            ok, msg = server.restart_ticket("TKT-RESTART")
            assert ok, msg

        # Artifacts should be gone.
        assert not (state_dir / "prd-TKT-RESTART.md").exists()
        assert not (state_dir / "tasks-TKT-RESTART.json").exists()
        assert not (state_dir / "architecture-TKT-RESTART.md").exists()
        assert not (server.get_ticket_snapshot_path("TKT-RESTART")).exists()

        # Ticket should be back to ready-for-work and a new run completed.
        board = server.load_board()
        ticket = board["tickets"][0]
        assert ticket["status"] == "ready-for-work"

        # Give the stub thread a moment to finish.
        for _ in range(50):
            state = server.load_run_state()
            if state.get("status") == "completed":
                break
            time.sleep(0.05)
        state = server.load_run_state()
        assert state.get("status") == "completed"
        assert state.get("ticketId") == "TKT-RESTART"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
```

### Step 4.2: Run tests

```bash
cd dashboard
python -m pytest tests/test_ticket_restart.py -v
```

---

## Task 5: Final verification and commit

- Run full test suite: `python -m pytest tests/ -q`
- Verify no syntax errors: `python -m py_compile server.py`
- Commit all changes with a clear message and push.

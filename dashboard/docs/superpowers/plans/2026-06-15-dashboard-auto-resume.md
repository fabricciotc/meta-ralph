# Dashboard Auto-Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the meta-ralph dashboard automatically resume a multi-agent run after a server restart or when the user clicks "Restart" on an agent/orchestrator while no runner thread is active.

**Architecture:** Add a `resume` mode to `AgentRunner` that reads the existing `run-state.json` and jumps to the phase that was in progress instead of starting from zero. Wire the restart endpoint and server startup to trigger this resume when the current ticket is not in `backlog`/`done` and the previous failure was caused by an interruption.

**Tech Stack:** Python 3.13, Flask, SocketIO, threading.

---

## Task 1: Add resume support to `AgentRunner`

**Files:**
- Modify: `server.py:693-699` (`AgentRunner.__init__`)
- Modify: `server.py:1122-1237` (`AgentRunner.run`)

- [ ] **Step 1: Accept a `resume` flag in the constructor**

```python
def __init__(self, ticket, resume=False):
    super().__init__(daemon=True)
    self.ticket = ticket
    self.ticket_id = ticket["id"]
    self.resume = bool(resume)
    self.kimi = find_kimi_cli()
    ...
```

- [ ] **Step 2: Skip full state reset when resuming**

In `run()`, wrap the initialization block (lines 1125-1158) so it only executes when `not self.resume`. When resuming, still call `_start_runtime_heartbeat()` and set `orchestrator` to `running`.

```python
def run(self):
    try:
        if not self.resume:
            # existing full reset block
            ...
        else:
            self.log(f"Reanudando run para {self.ticket_id} desde estado existente.")
            update_run_state({"active": True, "status": "in-progress", "currentAgent": "orchestrator"})
            self._ensure_agent("orchestrator", "Orchestrator Principal", "orchestrator", None, "running", 75)
            self._start_runtime_heartbeat()
            self._resume_loop()
            return
        ...
```

- [ ] **Step 3: Run the server and verify no syntax errors**

Run: `./venv/bin/python -m py_compile server.py`
Expected: no output (success).

---

## Task 2: Implement `_resume_loop()`

**Files:**
- Modify: `server.py` inside `AgentRunner` (add method after `run`)

- [ ] **Step 1: Add the resume dispatcher**

```python
def _resume_loop(self):
    state = load_run_state()
    review = state.get("designReview") or {}
    current_status = state.get("status")

    # Case A: we had not finished design review -> redo architect + review + planner + execution
    if not review.get("answered"):
        self._agent_log("orchestrator", "Reanudando desde Architecture/Design Review.")
        self.set_phase("architect", "in-design", 40)
        self.run_architect()
        if self._should_stop():
            return
        prd_path = get_meta_dir() / "state" / f"prd-{self.ticket_id}.md"
        questions = self._generate_design_questions(prd_path)
        answers = self._wait_for_design_answers(questions, timeout_seconds=60)
        if self._should_stop():
            return
        self.log(f"Respuestas de design review: {answers}")
        self._run_planner_and_execution()
        return

    # Case B: design review was already answered -> skip directly to planner + execution
    self._agent_log("orchestrator", "Reanudando desde Planning/Execution.")
    self.set_phase("project-manager", "in-design", 60)
    self._run_planner_and_execution()
```

- [ ] **Step 2: Add `_run_planner_and_execution()` helper**

```python
def _run_planner_and_execution(self):
    self.run_planner()
    if self._should_stop():
        self.log("Run detenido por solicitud del usuario tras Planning.", "warning")
        return
    self._agent_log("orchestrator", "Fase 4/5: Parallel Execution — implementando tareas en worktrees aislados.")
    update_ticket_status(self.ticket_id, "in-progress")
    self.set_phase("engineer-squad", "in-progress", 75)
    self.run_execution()
    if self._should_stop():
        self.log("Run detenido por solicitud del usuario tras Execution.", "warning")
        return
    self._agent_log("orchestrator", "Fase 5/5: QA Review — revisando integración del batch.")
    self.set_phase("qa-engineer", "in-review", 90)
    self.run_qa()
    if self._should_stop():
        self.log("Run detenido por solicitud del usuario tras QA.", "warning")
        return
    update_ticket_status(self.ticket_id, "done")
    self._update_agent("orchestrator", status="done", progress=100, log="Loop completado. Ticket marcado como Done.", log_level="success")
    self.set_phase(None, "completed", 100)
    self.log("Loop completado. Ticket marcado como Done.", "success")
```

- [ ] **Step 3: Compile again**

Run: `./venv/bin/python -m py_compile server.py`
Expected: no output.

---

## Task 3: Make execution reuse already-completed tasks

**Files:**
- Modify: `server.py:2275-2334` (`_execute_tasks_parallel`)

- [ ] **Step 1: Seed task status from existing engineer agents**

After `status = {t["id"]: "queued" for t in tasks}`, add:

```python
with run_lock:
    state = load_run_state()
    for t in tasks:
        tid = t["id"]
        agent_id = f"engineer-{tid}"
        agent = next((a for a in state.get("agents", []) if a.get("id") == agent_id), None)
        if agent and agent.get("status") == "done":
            status[tid] = "done"
            results[tid] = True
            self.log(f"Tarea {tid} ya completada; se omite en la reanudación.")
        elif agent and agent.get("status") == "failed":
            status[tid] = "failed"
            results[tid] = False
            self.log(f"Tarea {tid} había fallado; se omitirá (puede reiniciarse manualmente).")
```

- [ ] **Step 2: Compile**

Run: `./venv/bin/python -m py_compile server.py`
Expected: no output.

---

## Task 4: Add global helpers to start/resume a run

**Files:**
- Modify: `server.py:2645-2668` (`start_automatic_run`)
- Modify: `server.py:2669-2715` (`reset_run_state_to_idle`, `stop_active_run` area)

- [ ] **Step 1: Allow `start_automatic_run` to receive a resume flag**

```python
def start_automatic_run(ticket, resume=False):
    global _active_run_thread
    ...
    _active_run_thread = AgentRunner(ticket, resume=resume)
    _active_run_thread.start()
```

- [ ] **Step 2: Add `resume_run(ticket)` helper**

```python
def resume_run(ticket):
    """Reanuda un run previamente interrumpido para el ticket dado."""
    global _active_run_thread
    if _active_run_thread and _active_run_thread.is_alive():
        return False, "Ya hay un runner activo"
    state = load_run_state()
    if state.get("ticketId") != ticket["id"]:
        return False, "El ticket no coincide con run-state"
    start_automatic_run(ticket, resume=True)
    return True, "Run reanudado"
```

- [ ] **Step 3: Compile**

Run: `./venv/bin/python -m py_compile server.py`
Expected: no output.

---

## Task 5: Restart endpoint should resume when no runner is active

**Files:**
- Modify: `server.py:3153-3175` (`api_restart_agent`)

- [ ] **Step 1: Resume orchestrator/engineer-squad/project-manager restarts**

Replace the no-runner branch with:

```python
runner = _active_run_thread
if runner and runner.is_alive() and runner.ticket_id == ticket_id:
    ok = runner._restart_agent(agent_id)
    ...

# No hay runner activo: reanudar el loop si el agente es un coordinador de fase.
if agent_id in ("orchestrator", "engineer-squad", "project-manager"):
    ok, msg = resume_run(ticket)
    if not ok:
        return jsonify({"error": msg}), 409
    return jsonify({"ok": True, "agentId": agent_id, "resumed": True, "message": "Run reanudado desde el estado anterior."})

# Reinicio puntual de un agente sin runner activo
if agent_id.startswith("engineer-"):
    temp_runner = AgentRunner(ticket, resume=True)
    ok = temp_runner._restart_agent(agent_id)
    if not ok:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({"ok": True, "agentId": agent_id})

return jsonify({"error": "No hay runner activo para reiniciar este agente"}), 409
```

- [ ] **Step 2: Compile**

Run: `./venv/bin/python -m py_compile server.py`
Expected: no output.

---

## Task 6: Auto-resume on server startup

**Files:**
- Modify: `server.py:3243-3260` (initialization block at the bottom)

- [ ] **Step 1: After loading board/run-state, attempt auto-resume**

At the end of the initialization block, after `reset_run_state_to_idle()` or `stop_active_run(...)`:

```python
# Auto-resume runs that were interrupted by a server restart
state = load_run_state()
if state.get("status") == "failed" and state.get("ticketId"):
    last_log = ""
    for entry in reversed(state.get("logs", [])):
        if entry.get("level") == "error" or entry.get("level") == "warning":
            last_log = entry.get("message", "")
            break
    if "reinicio del servidor" in last_log or "interrumpido" in last_log:
        board = load_board()
        ticket = next((t for t in board.get("tickets", []) if t.get("id") == state["ticketId"]), None)
        if ticket and ticket.get("status") not in ("backlog", "done"):
            append_log(f"[AUTO-RESUME] Reanudando {ticket['id']} tras reinicio del servidor.", "warning")
            start_automatic_run(ticket, resume=True)
```

- [ ] **Step 2: Compile and start server**

Run: `./venv/bin/python -m py_compile server.py && ./venv/bin/python server.py --port 5050 --no-browser`
Expected: server starts; if `run-state.json` is failed because of a restart, it auto-resumes.

---

## Task 7: Optional UI feedback for resumed runs

**Files:**
- Modify: `static/app.js` (around `restartAgent`)

- [ ] **Step 1: Show a toast/notification when a restart triggers a full run resume**

In `restartAgent`, after the fetch, if `data.resumed` is true, show a transient status message (e.g., update `#runStatus` text or call a `showToast("Run reanudado desde el estado anterior")`).

```javascript
const data = await res.json();
if (data.resumed) {
  showToast(data.message || "Run reanudado desde el estado anterior");
}
```

- [ ] **Step 2: Reload dashboard and verify the notification appears**

Open `http://localhost:5050`, click restart on `orchestrator` while the run is failed, and confirm the modal closes and a resume toast appears.

---

## Self-Review

1. **Spec coverage:**
   - Restart button resumes the loop when no runner is active → Task 5.
   - Agents auto-resume after a server restart → Task 6.
   - Already-completed work (e.g. T1) is not redone → Task 3.
2. **Placeholder scan:** No TODO/TBD; each step has concrete code.
3. **Type consistency:** `resume` is a boolean everywhere; `start_automatic_run` signature updated in Tasks 4 and 6.

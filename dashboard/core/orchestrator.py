#!/usr/bin/env python3
"""MetaGPT-style orchestrator for the meta-ralph software factory loop.

The orchestrator drives the five phases of the loop using Environment +
Role/Action classes:

1. PM Analysis        -> pm_analysis.run_pm_analysis (roles internally)
2. Architecture       -> ArchitectRole
3. Planning           -> PlannerRole
4. Execution          -> EngineerRole (parallel task scheduling)
5. QA Review          -> QARole

It is designed to be server-agnostic: all dashboard/state integration is done
via the ``callbacks`` dictionary passed by server.py.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from core import pm_analysis
from core.environment import Environment
from core.models import Message
from core.roles.architect_role import ArchitectRole
from core.roles.planner_role import PlannerRole
from core.roles.engineer_role import EngineerRole
from core.roles.qa_role import QARole
from core.roles.dispatcher_role import DispatcherRole
from core.roles.monitor_role import MonitorRole
from core.roles.recovery_role import RecoveryRole
from core.roles.engineer_squad_role import EngineerSquadRole
from core.runners.registry import BackendRegistry
from core.skills_registry import SkillsRegistry
from core.context import Context


class Orchestrator(threading.Thread):
    """Thread that executes the full MetaGPT-style pipeline for a ticket."""

    def __init__(
        self,
        ticket: Dict[str, Any],
        resume: bool = False,
        runner_factory: Optional[Callable] = None,
        callbacks: Optional[Dict[str, Any]] = None,
        backend_registry: Optional[BackendRegistry] = None,
        skills_registry: Optional[SkillsRegistry] = None,
    ):
        super().__init__(daemon=True)
        self.ticket = ticket
        self.ticket_id = ticket["id"]
        self.resume = bool(resume)
        self.runner_factory = runner_factory
        self.callbacks = callbacks or {}
        self.backend_registry = backend_registry or BackendRegistry.default()
        self.skills_registry = skills_registry or SkillsRegistry()

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._resume_event = threading.Event()

        self.env: Optional[Environment] = None
        self._max_rounds_per_phase = 25
        self._max_qa_rounds = 3

        self.context = Context(
            ticket=ticket,
            callbacks=self.callbacks,
            backend_registry=self.backend_registry,
            skills_registry=self.skills_registry,
            prd_path=self._prd_path(),
            architecture_path=self._architecture_path(),
            tasks_path=self._tasks_path(),
            repo_path=self._repo_path(),
            branch=self._branch(),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        self._resume_event.set()

    def pause(self) -> None:
        self._pause_event.set()
        self._resume_event.clear()

    def resume(self) -> None:
        self._pause_event.clear()
        self._resume_event.set()

    def _should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _is_paused(self) -> bool:
        return self._pause_event.is_set()

    def _check_pause(self) -> None:
        if not self._is_paused():
            return
        self.log(f"Ticket {self.ticket_id} paused. Waiting for resume...")
        while self._is_paused() and not self._should_stop():
            self._resume_event.wait(timeout=1.0)
            self._resume_event.clear()
        if not self._should_stop():
            self.log(f"Ticket {self.ticket_id} resumed.")

    def _should_stop_or_pause(self) -> bool:
        self._check_pause()
        return self._should_stop()

    # ------------------------------------------------------------------
    # Callback helpers
    # ------------------------------------------------------------------
    def _callback(self, name: str, *args, **kwargs) -> Any:
        fn = self.callbacks.get(name)
        if fn is None:
            return None
        return fn(*args, **kwargs)

    def log(self, message: str, level: str = "info") -> None:
        self._callback("log", f"[{self.ticket_id}] {message}", level)

    def _set_phase(self, agent: str, status: str, progress: int) -> None:
        self._callback("set_phase", agent, status, progress)

    def _ensure_agent(self, agent_id: str, name: str, role: str, parent_id: Optional[str] = None, status: str = "queued", progress: int = 0) -> None:
        self._callback("ensure_agent", agent_id, name, role, parent_id, status, progress)

    def _update_agent(self, agent_id: str, **kwargs) -> None:
        self._callback("update_agent", agent_id, **kwargs)

    def _request_design_review(self, questions: List[Dict[str, Any]], timeout_seconds: int = 60) -> Dict[str, str]:
        return self._callback("request_design_review", questions, timeout_seconds) or {}

    def _collect_outputs(self, agent_id: str, repo_path: str) -> None:
        self._callback("collect_outputs", agent_id, repo_path)

    def _get_dependency_context(self, deps: List[str]) -> str:
        return self._callback("get_dependency_context", deps) or ""

    def _infer_role_from_phase(self, phase_name: str) -> str:
        mapping = {
            "pm_research": "pm_research",
            "pm_consolidate": "product_manager",
            "architect": "architect",
            "design_review": "architect",
            "planning": "project_manager",
            "engineer": "engineer",
            "qa_review": "qa",
            "qa_correction": "qa",
        }
        for key, role in mapping.items():
            if key in phase_name.lower():
                return role
        return "engineer"

    def _run_ai(self, prompt: str, phase_name: str, timeout_seconds: int, agent_id: Optional[str] = None) -> Optional[str]:
        """Execute a prompt through the configured AI backends with skill prefix injection."""
        role = self._infer_role_from_phase(phase_name)
        supports = self.backend_registry.supports_skill_activation()
        prefix = self.skills_registry.get_prompt_prefix(role, supports_skill_activation=supports)
        full_prompt = f"{prefix}\n\n{prompt}" if prefix else prompt

        # Allow server callbacks to override (legacy/local testing hook).
        callback_run = self.callbacks.get("run_ai")
        if callback_run:
            return callback_run(full_prompt, phase_name, timeout_seconds, agent_id)

        return self.backend_registry.run_prompt(
            full_prompt,
            phase_name=phase_name,
            timeout_seconds=timeout_seconds,
            agent_id=agent_id,
        )

    # ------------------------------------------------------------------
    # Core run
    # ------------------------------------------------------------------
    def run(self) -> None:
        try:
            if self.runner_factory:
                # Backward-compatible wrapper mode during transition.
                self._run_legacy_wrapper()
                return

            self._callback("on_started", self.ticket)
            self._set_phase("orchestrator", "in-design", 5)
            self._ensure_agent("orchestrator", "Main Orchestrator", "orchestrator", None, "running", 5)
            self.log("Ticket moved to Ready for work. Starting software factory loop...")

            # Initialize the shared Environment and coordinator swarm.
            self.env = Environment()
            self.env.add_role(DispatcherRole(
                ticket_id=self.ticket_id,
                ticket_title=self.ticket.get("title", ""),
                ticket_description=self.ticket.get("description", ""),
            ))
            self.env.add_role(MonitorRole(max_idle_rounds=5))
            self.env.add_role(RecoveryRole(max_retries=2))
            self.env.publish_message(Message(
                content=f"Ticket {self.ticket_id} ready",
                sent_from="orchestrator",
                cause_by="ticket_ready",
                send_to={"dispatcher"},
                metadata={"ticket_id": self.ticket_id},
            ))
            # Let the dispatcher publish the initial prd_ready trigger.
            self._run_environment_rounds(max_rounds=3)

            state = self._load_resume_state()

            if state.get("phase") in (None, "pm_analysis"):
                self._run_phase_1_pm_analysis()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "architecture"
                self._save_resume_state(state)

            if state.get("phase") == "architecture":
                self._run_phase_2_architecture()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "design_review"
                self._save_resume_state(state)

            if state.get("phase") == "design_review":
                self._run_phase_2_5_design_review()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "planning"
                self._save_resume_state(state)

            if state.get("phase") == "planning":
                self._run_phase_3_planning()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "execution"
                self._save_resume_state(state)

            if state.get("phase") == "execution":
                self._run_phase_4_execution()
                if self._should_stop_or_pause():
                    return
                state["phase"] = "qa"
                self._save_resume_state(state)

            if state.get("phase") == "qa":
                self._run_phase_5_qa()
                if self._should_stop_or_pause():
                    return

            self._set_phase("orchestrator", "completed", 100)
            self._update_agent("orchestrator", status="done", progress=100, log="Loop completed. Ticket marked as Done.", log_level="success")
            self._callback("on_complete", True)
            self.log("Loop completed. Ticket marked as Done.", "success")

        except Exception as exc:
            self.log(f"Loop error: {exc}", "error")
            self._update_agent("orchestrator", status="failed", log=f"Loop error: {exc}", log_level="error")
            self._callback("on_complete", False)

    def _run_legacy_wrapper(self) -> None:
        self.runner = self.runner_factory(self.ticket, self.resume)
        self.runner.start()
        self.runner.join()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _request_user_clarification(self, question: str, timeout_seconds: int = 60) -> str:
        """Escalate a doubt to the user and block until an answer is received."""
        fn = self.callbacks.get("request_clarification")
        if fn is None:
            return ""
        return fn(question, timeout_seconds)

    def _meta_dir(self) -> Path:
        return Path.cwd() / "scripts" / "meta-ralph"

    def _prd_path(self) -> Path:
        return self._meta_dir() / "state" / f"prd-{self.ticket_id}.md"

    def _architecture_path(self) -> Path:
        return self._meta_dir() / "state" / f"architecture-{self.ticket_id}.md"

    def _tasks_path(self) -> Path:
        return self._meta_dir() / "state" / f"tasks-{self.ticket_id}.json"

    def _repo_path(self) -> str:
        return self.ticket.get("repoPath", "")

    def _branch(self) -> str:
        return self.ticket.get("branch", "")

    def _run_environment_rounds(self, max_rounds: Optional[int] = None) -> None:
        max_rounds = max_rounds or self._max_rounds_per_phase
        for i in range(max_rounds):
            if self._should_stop_or_pause():
                return
            active = asyncio.run(self.env.run_round(context=self.context))
            if not active and self.env.is_idle():
                break

    def _find_messages(self, cause_by: str) -> List[Message]:
        return [m for m in self.env.history() if m.cause_by == cause_by]

    def _latest_message(self, cause_by: str) -> Optional[Message]:
        for m in reversed(self.env.history()):
            if m.cause_by == cause_by:
                return m
        return None

    # ------------------------------------------------------------------
    # Resume state (minimal on-disk checkpoint)
    # ------------------------------------------------------------------
    def _resume_state_path(self) -> Path:
        return self._meta_dir() / "state" / f"orchestrator-state-{self.ticket_id}.json"

    def _load_resume_state(self) -> Dict[str, Any]:
        path = self._resume_state_path()
        if self.resume and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"phase": None}

    def _save_resume_state(self, state: Dict[str, Any]) -> None:
        path = self._resume_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not save resume state: {exc}", "warning")

    # ------------------------------------------------------------------
    # Phase 1: PM Analysis
    # ------------------------------------------------------------------
    def _run_phase_1_pm_analysis(self) -> None:
        self.log("Phase 1/5: PM Analysis: generating a detailed plan with subagents.")
        self._set_phase("pm-research-agents", "in-design", 10)
        self._ensure_agent("pm-research-agents", "PM Research Agents", "lead", "orchestrator", "running", 10)
        for sub_id, sub_name, _ in pm_analysis.DEFAULT_SUBAGENTS:
            self._ensure_agent(sub_id, sub_name, "sub", "pm-research-agents", "queued", 0)

        def log_callback(message: str, level: str = "info"):
            self.log(message, level)

        generated_prd = pm_analysis.run_pm_analysis(
            self.ticket,
            run_ai=self._run_ai,
            max_rounds=10,
            log_callback=log_callback,
        )

        if generated_prd and generated_prd.exists():
            self.log(f"Detailed plan saved at {generated_prd}")
        else:
            self.log("No PRD was generated; using local fallback.", "warning")
            pm_analysis.write_fallback_prd(self._prd_path(), self.ticket.get("title", ""), self.ticket.get("description", ""))

        for sub_id, sub_name, _ in pm_analysis.DEFAULT_SUBAGENTS:
            self._update_agent(sub_id, status="done", progress=100, log=f"{sub_name} completed.")
        self._update_agent("pm-research-agents", status="done", progress=100, log="PM Research Agents consolidated the PRD.")
        self._set_phase("pm-lead", "in-design", 35)

    # ------------------------------------------------------------------
    # Phase 2: Architecture
    # ------------------------------------------------------------------
    def _run_phase_2_architecture(self) -> None:
        self.log("Phase 2/5: Architecture: defining global technical patterns.")
        self._set_phase("architect", "in-design", 40)
        self._ensure_agent("architect", "Architect", "lead", "orchestrator", "running", 40)

        prd_path = self._prd_path()
        architecture_path = self._architecture_path()

        if self.env is None:
            self.env = Environment()
        architect = ArchitectRole(
            run_ai=self._run_ai,
            prd_path=prd_path,
            architecture_path=architecture_path,
            ticket_title=self.ticket.get("title", ""),
            ticket_description=self.ticket.get("description", ""),
            ticket_id=self.ticket_id,
            phase_name="architect",
            timeout_seconds=600,
        )
        self.env.add_role(architect)

        self.env.publish_message(Message(
            content=f"PRD ready at {prd_path}",
            sent_from="orchestrator",
            cause_by="prd_ready",
            send_to={"architect"},
            metadata={"path": str(prd_path), "ticket_id": self.ticket_id},
        ))

        self._run_environment_rounds()

        ready_msg = self._latest_message("architecture_ready")
        if ready_msg:
            self._update_agent("architect", status="done", progress=100, log=f"Architecture saved at {ready_msg.metadata.get('path', architecture_path)}.")
        else:
            self._update_agent("architect", status="done", progress=100, log="Architecture finished.")

    # ------------------------------------------------------------------
    # Phase 2.5: Design Review
    # ------------------------------------------------------------------
    def _run_phase_2_5_design_review(self) -> None:
        # If the architect emitted design_review_requested, ask the user.
        review_request = self._latest_message("design_review_requested")
        if not review_request:
            self.log("No pending design decisions detected; continuing.")
            return

        questions = review_request.metadata.get("questions", [])
        if not questions:
            self.log("No design questions detected; continuing.")
            return

        self.log("Phase 2.5/5: Design Review: waiting for technical decision confirmation.")
        self._set_phase("design-review", "design-review", 55)

        formatted = [
            {"id": f"q{i}", "question": q, "assumedAnswer": "", "inputType": "text"}
            for i, q in enumerate(questions, start=1)
        ]
        answers = self._request_design_review(formatted, timeout_seconds=60)

        if not answers:
            answers = {q["id"]: q.get("assumedAnswer", "") for q in formatted}

        answers_text = "\n".join(f"Q: {q}\nA: {answers.get(f'q{i}', '')}" for i, q in enumerate(questions, start=1))
        self.env.publish_message(Message(
            content=answers_text,
            sent_from="orchestrator",
            cause_by="design_review_answered",
            send_to={"architect"},
            metadata={"answers": answers, "ticket_id": self.ticket_id},
        ))

        self._run_environment_rounds()
        self.log(f"Design review answers: {answers}")

    # ------------------------------------------------------------------
    # Phase 3: Planning
    # ------------------------------------------------------------------
    def _run_phase_3_planning(self) -> None:
        self.log("Phase 3/5: Planning & Dispatch: building batches and dependency DAG.")
        self._set_phase("project-manager", "in-design", 60)
        self._ensure_agent("project-manager", "Project Manager", "lead", "orchestrator", "running", 60)

        # Reuse existing environment if architecture ran; otherwise create fresh.
        if self.env is None:
            self.env = Environment()

        planner = PlannerRole(
            run_ai=self._run_ai,
            ticket_id=self.ticket_id,
            ticket_title=self.ticket.get("title", ""),
            ticket_description=self.ticket.get("description", ""),
            prd_path=self._prd_path(),
            tasks_path=self._tasks_path(),
            phase_name="planning",
            timeout_seconds=600,
        )
        self.env.add_role(planner)

        # Trigger planner with the PRD (and architecture if present).
        metadata: Dict[str, Any] = {"path": str(self._prd_path()), "ticket_id": self.ticket_id}
        architecture_path = self._architecture_path()
        if architecture_path.exists():
            metadata["architecture_path"] = str(architecture_path)

        self.env.publish_message(Message(
            content=f"Plan tasks from {self._prd_path()}",
            sent_from="orchestrator",
            cause_by="prd_ready",
            send_to={"planner"},
            metadata=metadata,
        ))

        # If architecture is available, also publish architecture_ready so the planner uses it.
        if architecture_path.exists():
            self.env.publish_message(Message(
                content=f"Architecture ready at {architecture_path}",
                sent_from="orchestrator",
                cause_by="architecture_ready",
                send_to={"planner"},
                metadata={"path": str(architecture_path), "ticket_id": self.ticket_id},
            ))

        self._run_environment_rounds()

        plan_msg = self._latest_message("plan_ready")
        tasks: List[Dict[str, Any]] = []
        if plan_msg and plan_msg.metadata.get("path"):
            try:
                tasks = json.loads(Path(plan_msg.metadata["path"]).read_text(encoding="utf-8"))
            except Exception as exc:
                self.log(f"Could not read task plan: {exc}", "warning")

        if not tasks:
            tasks = self._fallback_tasks()
            self._tasks_path().write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")

        self._update_agent("project-manager", status="done", progress=100, log=f"Generated plan with {len(tasks)} tasks.")
        self._set_phase("project-manager", "in-progress", 65)

    def _fallback_tasks(self) -> List[Dict[str, Any]]:
        title = self.ticket.get("title", "Implementation")
        description = self.ticket.get("description", "")
        return [
            {
                "id": f"{self.ticket_id}-T1",
                "title": f"Implement: {title}",
                "description": description,
                "dependencies": [],
                "files_to_touch": [],
                "complexity": "M",
                "qa_checklist": ["Validate that it satisfies the ticket description."],
            },
            {
                "id": f"{self.ticket_id}-T2",
                "title": "Add unit tests",
                "description": "Minimum coverage for the implemented change.",
                "dependencies": [f"{self.ticket_id}-T1"],
                "files_to_touch": [],
                "complexity": "S",
                "qa_checklist": ["Tests pass locally."],
            },
        ]

    # ------------------------------------------------------------------
    # Phase 4: Execution
    # ------------------------------------------------------------------
    def _run_phase_4_execution(self) -> None:
        self.log("Phase 4/5: Parallel Execution: implementing tasks in parallel.")
        self._set_phase("engineer-squad", "in-progress", 75)
        self._ensure_agent("engineer-squad", "Engineer Squad", "lead", "orchestrator", "running", 75)

        tasks_path = self._tasks_path()
        if not tasks_path.exists():
            self.log("tasks.json was not found; skipping execution.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No tasks to execute.")
            return

        try:
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.log(f"Error reading tasks.json: {exc}", "error")
            self._update_agent("engineer-squad", status="failed", progress=100, log=f"Error reading tasks: {exc}")
            return

        if not tasks:
            self.log("Planner did not generate tasks; skipping execution.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No tasks to execute.")
            return

        repo_path = self._repo_path()
        if not repo_path:
            self.log("No repository configured; skipping execution.", "warning")
            self._update_agent("engineer-squad", status="done", progress=100, log="No repository configured.")
            return

        if self.env is None:
            self.env = Environment()

        # Add the squad lead so it coordinates engineers and resolves blockers.
        squad = EngineerSquadRole(
            run_ai=self._run_ai,
            ticket_id=self.ticket_id,
            ticket_title=self.ticket.get("title", ""),
            ticket_description=self.ticket.get("description", ""),
            prd_path=self._prd_path(),
            tasks=tasks,
            max_retries=2,
            phase_name="engineer-squad",
            timeout_seconds=300,
            request_clarification=self._request_user_clarification,
        )
        self.env.add_role(squad)

        task_by_id = {t["id"]: t for t in tasks}
        status: Dict[str, str] = {t["id"]: "queued" for t in tasks}
        completed: Set[str] = set()
        failed: Set[str] = set()
        max_workers = 10
        running_threads: Dict[str, threading.Thread] = {}
        lock = threading.Lock()
        stop_event = threading.Event()

        def can_run(task: Dict[str, Any]) -> bool:
            deps = task.get("dependencies", []) or []
            return all(status.get(d) == "done" for d in deps)

        def run_task(task: Dict[str, Any]) -> None:
            tid = task["id"]
            agent_id = f"engineer-{tid}"
            self._ensure_agent(agent_id, f"Engineer {tid}", "sub", "engineer-squad", "running", 0)
            self._update_agent(agent_id, progress=20, log=f"Starting task: {task.get('title', tid)}")

            deps = task.get("dependencies", []) or []
            dependencies_context = self._get_dependency_context(deps)

            role = EngineerRole(
                role_id=agent_id,
                focus=task.get("title", tid),
                run_ai=self._run_ai,
                repo_path=repo_path,
                branch_prefix="feature",
                update_agent=lambda agent_id, **kwargs: self._update_agent(agent_id, **kwargs),
                phase_name=f"engineer-{tid}",
                timeout_seconds=1800,
            )
            self.env.add_role(role)

            branch = f"feature/{self.ticket_id}-{tid}".lower()
            metadata = {
                "task": task,
                "ticket_id": self.ticket_id,
                "ticket_title": self.ticket.get("title", ""),
                "ticket_description": self.ticket.get("description", ""),
                "repo_path": repo_path,
                "branch": branch,
                "dependencies_context": dependencies_context,
                "prd_path": str(self._prd_path()),
                "architecture_path": str(self._architecture_path()) if self._architecture_path().exists() else None,
            }

            self.env.publish_message(Message(
                content=f"Implement task {tid}",
                sent_from="orchestrator",
                cause_by="task_assigned",
                send_to={agent_id},
                metadata=metadata,
            ))

            # Run rounds until this task is completed or max rounds exhausted.
            # The squad lead may retry failed tasks via squad_instruction messages.
            for _ in range(self._max_rounds_per_phase):
                if stop_event.is_set() or self._should_stop_or_pause():
                    break
                asyncio.run(self.env.run_round(context=self.context))
                # Check if our task was completed in this round.
                latest_completed = None
                for m in reversed(self.env.history()):
                    if m.metadata.get("task_id") != tid:
                        continue
                    if m.cause_by == "task_completed":
                        latest_completed = m
                        break
                if latest_completed:
                    self._update_agent(agent_id, status="done", progress=100, log=f"Task {tid} completed.")
                    self._collect_outputs(agent_id, repo_path)
                    with lock:
                        status[tid] = "done"
                        completed.add(tid)
                    return

            # If we exhausted rounds without completion, mark failed.
            self._update_agent(agent_id, status="failed", progress=100, log=f"Task {tid} did not finish in time.")
            with lock:
                status[tid] = "failed"
                failed.add(tid)
            stop_event.set()

        pending = set(t["id"] for t in tasks if status.get(t["id"]) == "queued")
        self.log(f"[execution] {len(pending)} pending tasks.")

        while pending or running_threads:
            if stop_event.is_set() or self._should_stop_or_pause():
                for t in list(running_threads.values()):
                    t.join(timeout=5)
                with lock:
                    for tid in list(pending):
                        status[tid] = "blocked"
                        self._ensure_agent(f"engineer-{tid}", f"Engineer {tid}", "sub", "engineer-squad", "blocked", 0)
                        self._update_agent(f"engineer-{tid}", status="blocked", progress=0, log="Blocked by dependency failure.")
                break

            while len(running_threads) < max_workers and pending:
                ready = [task_by_id[tid] for tid in pending if can_run(task_by_id[tid])]
                if not ready:
                    break
                task = ready[0]
                tid = task["id"]
                pending.remove(tid)
                with lock:
                    status[tid] = "running"
                t = threading.Thread(target=run_task, args=(task,), daemon=True)
                running_threads[tid] = t
                t.start()

            if not running_threads:
                break

            done_threads = [tid for tid, t in running_threads.items() if not t.is_alive()]
            for tid in done_threads:
                del running_threads[tid]
            if not done_threads:
                time.sleep(0.5)

        successful = sum(1 for s in status.values() if s == "done")
        self.log(f"Parallel execution finished: {successful}/{len(tasks)} successful.")
        self._update_agent("engineer-squad", status="done", progress=100, log=f"Execution completed: {successful}/{len(tasks)}.")
        self._set_phase("engineer-squad", "in-progress", 85)

    # ------------------------------------------------------------------
    # Phase 5: QA Review
    # ------------------------------------------------------------------
    def _run_phase_5_qa(self) -> None:
        self.log("Phase 5/5: QA Review: reviewing batch integration.")
        self._set_phase("qa-engineer", "in-review", 90)
        self._ensure_agent("qa-engineer", "QA Engineer", "lead", "orchestrator", "running", 90)

        tasks_path = self._tasks_path()
        if not tasks_path.exists():
            self.log("tasks.json was not found; skipping QA.", "warning")
            self._update_agent("qa-engineer", status="done", progress=100, log="No tasks to review.")
            return

        try:
            tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.log(f"Error reading tasks.json: {exc}", "error")
            self._update_agent("qa-engineer", status="done", progress=100, log="Error reading tasks.")
            return

        repo_path = self._repo_path()
        branch = self._branch()

        # Publish review requests for every completed task.
        completed_by_task = {
            m.metadata.get("task_id"): m
            for m in self.env.history()
            if m.cause_by == "task_completed" and m.metadata.get("task_id")
        }
        review_requested = False
        for task in tasks:
            tid = task["id"]
            agent_id = f"engineer-{tid}"
            completed = completed_by_task.get(tid)
            build_output = completed.metadata.get("build_output", "") if completed else ""
            test_output = completed.metadata.get("test_output", "") if completed else ""
            self._ensure_agent(f"qa-{tid}", f"QA {tid}", "qa", "qa-engineer", "queued", 90)
            self.env.publish_message(Message(
                content=f"Review task {tid}",
                sent_from="orchestrator",
                cause_by="request_review",
                send_to={"qa-lead"},
                metadata={
                    "task_id": tid,
                    "task": task,
                    "repo_path": repo_path,
                    "branch": branch,
                    "diff": "",
                    "build_output": build_output,
                    "test_output": test_output,
                },
            ))
            review_requested = True

        if not review_requested:
            self.log("No tasks to review.")
            self._update_agent("qa-engineer", status="done", progress=100, log="No tasks to review.")
            return

        qa_lead = QARole(
            run_ai=self._run_ai,
            max_rounds=self._max_qa_rounds,
        )
        self.env.add_role(qa_lead)

        self._run_environment_rounds()

        approved = [m for m in self.env.history() if m.cause_by == "review_approved"]
        rejected = [m for m in self.env.history() if m.cause_by == "reject_with_feedback"]

        self.log(f"QA: {len(approved)} approved, {len(rejected)} rejected.")
        self._update_agent("qa-engineer", status="done", progress=100, log=f"QA Review completed: {len(approved)} approved, {len(rejected)} rejected.")
        self._set_phase("qa-engineer", "in-review", 95)

"""Audit trail for agent runs, appended to output/audit_trail.json.

One record per team run (a ticket, or a direct question to one agent). Each
record has:
- run metadata: id, kind, subject, model, start/end time, duration, status, error
- agent_runs: every agent that ran (Boss and each delegation), who asked it,
  its depth in the delegation chain, its task, loop steps, usage, and output
- events: a time-ordered log of every loop step, model response, tool call,
  tool result, delegation, and refusal, tagged with agent, depth, and step
- usage totals and the safety check result
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

from config import AUDIT_PATH

_FILE_LOCK = threading.Lock()
MAX_FIELD_CHARS = 6000  # long tool outputs are trimmed, never dropped


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _clip(value: Any) -> Any:
    """Keep audit entries JSON-safe and bounded."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    try:
        text = json.dumps(value, default=str)
    except TypeError:
        text = json.dumps(str(value))
    if len(text) <= MAX_FIELD_CHARS:
        return json.loads(text)
    return {"truncated": True, "chars": len(text), "preview": text[:MAX_FIELD_CHARS]}


class AuditRecorder:
    def __init__(self, kind: str, subject: str, model: str, ticket_id: int | None = None, path: Path = AUDIT_PATH,
                 listener: Callable[[AuditRecorder, dict], None] | None = None):
        self.path = path
        self.run_id = f"run-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.kind = kind
        self.subject = subject
        self.model = model
        self.ticket_id = ticket_id
        self.started_at = _now()
        self._t0 = time.perf_counter()
        self._seq = 0
        self.events: list[dict] = []
        self.agent_runs: dict[str, dict] = {}
        self.models_seen: set[str] = set()
        self.safety: dict | None = None
        self.listener = listener  # e.g. the board's live event feed

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def event(self, kind: str, *, agent: str | None = None, agent_run_id: str | None = None,
              depth: int | None = None, loop_step: int | None = None, **details: Any) -> None:
        self._seq += 1
        self.events.append({
            "seq": self._seq,
            "time": _now(),
            "elapsed_ms": self.elapsed_ms(),
            "kind": kind,
            "agent": agent,
            "agent_run_id": agent_run_id,
            "depth": depth,
            "loop_step": loop_step,
            **{k: _clip(v) for k, v in details.items()},
        })
        if self.listener:
            try:
                self.listener(self, self.events[-1])
            except Exception:  # a broken listener must never break an agent run
                pass

    @property
    def agent_run_count(self) -> int:
        return len(self.agent_runs)

    def start_agent(self, agent: str, task: str, parent_id: str | None, depth: int, chain: tuple[str, ...]) -> str:
        agent_run_id = f"{agent}-{len(self.agent_runs) + 1}"
        self.agent_runs[agent_run_id] = {
            "agent_run_id": agent_run_id,
            "agent": agent,
            "parent_agent_run_id": parent_id,
            "depth": depth,
            "chain": list(chain),
            "task": task,
            "started_at": _now(),
            "_t0": time.perf_counter(),
        }
        self.event("agent_start", agent=agent, agent_run_id=agent_run_id, depth=depth,
                   parent_agent_run_id=parent_id, chain=list(chain), task=task)
        return agent_run_id

    def finish_agent(self, agent_run_id: str, *, status: str, loop_steps: int, usage: Any = None,
                     output: Any = None, error: str | None = None) -> None:
        run = self.agent_runs[agent_run_id]
        run["finished_at"] = _now()
        run["duration_ms"] = int((time.perf_counter() - run.pop("_t0")) * 1000)
        run["status"] = status
        run["loop_steps"] = loop_steps
        run["usage"] = _clip(usage)
        run["output"] = _clip(output)
        if error:
            run["error"] = error
        self.event("agent_end", agent=run["agent"], agent_run_id=agent_run_id, depth=run["depth"],
                   status=status, duration_ms=run["duration_ms"], loop_steps=loop_steps, error=error,
                   output=output)

    def record(self, *, status: str, result: Any = None, error: str | None = None, usage: Any = None) -> dict:
        for run in self.agent_runs.values():  # agents cut off by an error
            if "_t0" in run:
                run["duration_ms"] = int((time.perf_counter() - run.pop("_t0")) * 1000)
                run["status"] = "interrupted"
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "subject": self.subject,
            "ticket_id": self.ticket_id,
            "model_configured": self.model,
            "models_used": sorted(self.models_seen),
            "started_at": self.started_at,
            "finished_at": _now(),
            "duration_ms": self.elapsed_ms(),
            "status": status,
            "error": error,
            "usage_totals": _clip(usage),
            "agent_run_count": len(self.agent_runs),
            "delegations": sum(1 for e in self.events if e["kind"] == "delegate"),
            "tool_calls": sum(1 for e in self.events if e["kind"] == "tool_call"),
            "safety_check": self.safety,
            "result": _clip(result),
            "agent_runs": list(self.agent_runs.values()),
            "events": self.events,
        }

    def save(self, record: dict) -> None:
        """Append this run to the audit file (a JSON list), writing atomically."""
        with _FILE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            runs: list = []
            if self.path.exists():
                try:
                    runs = json.loads(self.path.read_text(encoding="utf-8") or "[]")
                except json.JSONDecodeError:
                    backup = self.path.with_suffix(f".corrupt-{int(time.time())}.json")
                    self.path.replace(backup)
                    runs = []
            runs.append(record)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(runs, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

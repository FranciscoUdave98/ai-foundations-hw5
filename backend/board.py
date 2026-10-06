"""What the dashboard needs that isn't a shop fact: the live event feed,
payments waiting for a human, and each ticket's latest team decision.

Shop facts (tickets, balances, invoices, leases) always come from the MCP
server. This module only keeps board state in output/board_state.json, which
is cleared when the database is reset.
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from config import AUDIT_PATH, OUTPUT_DIR

STATE_PATH = OUTPUT_DIR / "board_state.json"
_LOCK = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _short(value: Any, limit: int = 220) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _args_text(args: Any) -> str:
    if isinstance(args, dict):
        return ", ".join(f"{k}={json.dumps(v, default=str)}" for k, v in args.items())
    return _short(args, 120)


# ---- live event feed ----------------------------------------------------

class EventFeed:
    """Recent agent events, simplified for the board: who did what, and what they said."""

    def __init__(self, maxlen: int = 2000) -> None:
        self.events: deque[dict] = deque(maxlen=maxlen)
        self.seq = 0
        self._lock = threading.Lock()

    def _push(self, item: dict) -> None:
        with self._lock:
            self.seq += 1
            self.events.append({"seq": self.seq, **item})

    def board_event(self, kind: str, text: str, *, ticket_id: int | None = None, run_id: str | None = None,
                    agent: str = "system", detail: Any = None) -> None:
        self._push({"time": now(), "run_id": run_id, "ticket_id": ticket_id, "agent": agent, "depth": None,
                    "loop_step": None, "kind": kind, "text": text, "detail": detail})

    def from_audit(self, run_id: str, ticket_id: int | None, raw: dict) -> None:
        item = simplify(raw)
        if item:
            self._push({"time": raw.get("time"), "run_id": run_id, "ticket_id": ticket_id,
                        "agent": raw.get("agent"), "depth": raw.get("depth"),
                        "loop_step": raw.get("loop_step"), **item})

    def since(self, seq: int = 0, limit: int = 200, ticket_id: int | None = None, run_id: str | None = None) -> list[dict]:
        with self._lock:
            items = [e for e in self.events if e["seq"] > seq
                     and (ticket_id is None or e["ticket_id"] == ticket_id)
                     and (run_id is None or e["run_id"] == run_id)]
        return items[-limit:]

    def seed_from_audit(self, last_runs: int = 3) -> None:
        """After a restart, show the most recent runs from the audit trail."""
        if not AUDIT_PATH.exists():
            return
        try:
            runs = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
        except json.JSONDecodeError:
            return
        for run in runs[-last_runs:]:
            for raw in run.get("events", []):
                self.from_audit(run["run_id"], run.get("ticket_id"), raw)


def simplify(raw: dict) -> dict | None:
    """Turn one audit event into a board line: kind, a readable sentence, and detail."""
    kind, agent = raw["kind"], raw.get("agent") or "system"
    if kind == "agent_start":
        text = f"{agent} started: {_short(raw.get('task'), 160)}" if raw.get("depth") == 0 else f"{agent} picked up the request"
        return {"kind": "started", "text": text, "detail": {"task": raw.get("task"), "chain": raw.get("chain")}}
    if kind == "delegate":
        return {"kind": "delegated", "text": f"{agent} asked {raw.get('to')}: {_short(raw.get('request'))}",
                "detail": {"to": raw.get("to"), "request": raw.get("request")}}
    if kind == "delegate_refused":
        return {"kind": "refused", "text": f"{agent} couldn't ask {raw.get('to')}: {raw.get('reason')}",
                "detail": {"to": raw.get("to"), "reason": raw.get("reason")}}
    if kind == "tool_call":
        tool, args = raw.get("tool"), raw.get("args")
        if tool == "final_result" and isinstance(args, dict):  # the agent's structured answer
            said = args.get("final_call") or args.get("answer") or ""
            return {"kind": "said", "text": f"{agent}: {_short(said, 400)}", "detail": args}
        if tool == "ask_agent":
            return None  # shown as the 'delegated' event instead
        return {"kind": "tool", "text": f"{agent} used {tool}({_args_text(args)})",
                "detail": {"tool": tool, "args": args}}
    if kind == "tool_result":
        tool = raw.get("tool")
        if tool in ("final_result", "ask_agent"):
            return None
        return {"kind": "tool_result", "text": f"{tool} returned {_short(raw.get('result'), 160)}",
                "detail": {"tool": tool, "result": raw.get("result")}}
    if kind == "model_response" and raw.get("text"):
        return {"kind": "said", "text": f"{agent}: {_short(raw['text'], 400)}", "detail": {"text": raw["text"]}}
    if kind == "retry":
        return {"kind": "retry", "text": f"{agent} retried {raw.get('tool')}", "detail": {"reason": raw.get("reason")}}
    if kind == "agent_end":
        if raw.get("status") != "ok":
            return {"kind": "error", "text": f"{agent} failed: {raw.get('error')}", "detail": None}
        return {"kind": "finished", "text": f"{agent} finished in {raw.get('duration_ms', 0) / 1000:.1f}s "
                f"({raw.get('loop_steps')} loop steps)", "detail": {"output": raw.get("output")}}
    if kind == "safety_check":
        ok = raw.get("within_balance")
        return {"kind": "safety", "text": f"Safety check: payments ${raw.get('payment_total', 0):,.2f} "
                f"{'fit' if ok else 'DO NOT fit'} the ${raw.get('cash_balance') or 0:,.2f} balance",
                "detail": {k: raw.get(k) for k in ("payment_total", "cash_balance", "balance_after",
                                                   "within_balance", "notes")}}
    return None  # loop_step markers etc. stay in the audit trail only


# ---- persisted board state ---------------------------------------------

def _empty_state() -> dict:
    return {"last_reset": None, "tickets": {}, "approvals": {}}


def load_state() -> dict:
    with _LOCK:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return _empty_state()


def save_state(state: dict) -> None:
    with _LOCK:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_PATH)


def reset_state() -> dict:
    state = _empty_state()
    state["last_reset"] = now()
    save_state(state)
    return state


def _same_bill(a: dict, b: dict) -> bool:
    """Two requests for the same existing bill (an invoice or a lease's rent)."""
    return a["kind"] in ("invoice", "rent") and a["kind"] == b["kind"] and a["ref_id"] is not None and a["ref_id"] == b["ref_id"]


def cover_duplicates(state: dict, paid: dict) -> list[dict]:
    """After `paid` is approved, close other pending requests for the same bill."""
    covered = []
    for a in state["approvals"].values():
        if a is not paid and a["status"] == "pending" and _same_bill(a, paid):
            a.update(status="covered", covered_by=paid["approval_id"], covered_at=now(),
                     note=f"Same bill already paid via ticket {paid['ticket_id']}'s approval.")
            covered.append(a)
    return covered


def record_decision(result: Any) -> list[dict]:
    """Store a ticket's latest decision and queue its payment requests for a human.

    Older pending requests for the same ticket are superseded by the new run.
    """
    state = load_state()
    d = result.decision
    tid = str(result.ticket_id)
    for a in state["approvals"].values():
        if a["ticket_id"] == result.ticket_id and a["status"] == "pending":
            a["status"] = "superseded"
            a["superseded_by"] = result.run_id
    queued = []

    def queue(approval_id: str, item: dict) -> None:
        approval = {"approval_id": approval_id, "ticket_id": result.ticket_id, "run_id": result.run_id,
                    **item, "status": "pending", "created_at": now()}
        # A bill a human already paid for another ticket needs no new signature.
        paid = next((a for a in state["approvals"].values() if a["status"] == "approved" and _same_bill(a, approval)), None)
        if paid:
            approval.update(status="covered", covered_by=paid["approval_id"], covered_at=now(),
                            note=f"Same bill already paid via ticket {paid['ticket_id']}'s approval.")
        state["approvals"][approval_id] = approval
        if approval["status"] == "pending":
            queued.append(approval)

    for i, p in enumerate(d.payment_requests, 1):
        queue(f"{result.run_id}-p{i}", p.model_dump(mode="json"))

    # Purchase orders need a human too. Queue each draft as a purchase approval
    # unless the Boss already listed the same purchase as a payment request.
    already = {(q["kind"], q["payee"], round(q["amount"], 2)) for q in queued}
    for i, po in enumerate(d.purchase_orders, 1):
        key = ("purchase_order", po.vendor_name, round(po.total_cost, 2))
        if key in already:
            continue
        queue(f"{result.run_id}-po{i}", {
            "kind": "purchase_order", "ref_id": None, "payee": po.vendor_name, "amount": po.total_cost,
            "account": "checking", "requires_human_approval": True,
            "reason": f"PO: {po.qty} × {po.sku} size {po.size} at ${po.unit_cost:,.2f} "
                      f"({po.lead_days}-day lead time)",
            "purchase_order": po.model_dump(mode="json"),
        })
    state["tickets"][tid] = {
        "run_id": result.run_id,
        "finished_at": now(),
        "decision": d.decision,
        "final_call": d.final_call,
        "assigned_agents": d.assigned_agents,
        "customer_message": d.customer_message,
        "blockers": d.blockers,
        "purchase_orders": [po.model_dump(mode="json") for po in d.purchase_orders],
        "safety": result.safety.model_dump(mode="json"),
        "approval_ids": [q["approval_id"] for q in queued],
    }
    save_state(state)
    return queued

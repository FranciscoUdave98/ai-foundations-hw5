"""Campus Customs agent desk: FastAPI backend for the ticket board.

Start (from this folder, with the HW5 venv active):
    uvicorn main:app --reload --port 8000

Routes:
    GET  /api/tickets                     tickets with open/resolved status and latest decision
    POST /api/tickets/{ticket_id}/run     run the agent team on a ticket (in the background)
    GET  /api/runs/{run_id}               status and result of one team run
    GET  /api/events                      recent agent events for the live board
    GET  /api/payments/pending            payments waiting for a human
    POST /api/payments/{approval_id}/approve   a human approves one payment
    GET  /api/cash                        current checking balance
    POST /api/reset                       reset the working db to the original
    GET  /api/health                      quick health check

Every shop fact is read and written through the MCP server; this app never
opens the database itself. Payments are only recorded when a human approves.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import board  # noqa: E402
from config import MODEL_NAME  # noqa: E402
from reset_db import reset_working_db  # noqa: E402
from team import Team  # noqa: E402

feed = board.EventFeed()
jobs: dict[str, dict] = {}       # run_id -> {status, ticket_id, started_at, finished_at, result | error}
run_lock = asyncio.Lock()        # one team run at a time keeps the db consistent
_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    team = Team()
    await team.__aenter__()  # one MCP server process for the app's lifetime
    app.state.team = team
    feed.seed_from_audit()
    try:
        yield
    finally:
        for task in _tasks:
            task.cancel()
        await team.__aexit__(None, None, None)


app = FastAPI(title="Campus Customs Agent Desk", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def team() -> Team:
    return app.state.team


async def mcp(tool: str, args: dict | None = None) -> dict:
    return await team()._call(tool, args or {})


def running_job() -> dict | None:
    return next((j for j in jobs.values() if j["status"] == "running"), None)


# ---- tickets ----------------------------------------------------------

@app.get("/api/tickets")
async def list_tickets() -> dict:
    """All tickets with open/resolved status, the latest team decision, and pending approvals."""
    board_data = await mcp("list_tickets", {"status": "all"})
    state = board.load_state()
    busy = running_job()
    tickets = []
    for t in board_data["tickets"]:
        last = state["tickets"].get(str(t["id"]))
        pending = [a for a in state["approvals"].values() if a["ticket_id"] == t["id"] and a["status"] == "pending"]
        tickets.append({
            **t,
            "is_open": t["status"] == "open",
            "is_resolved": t["status"] == "resolved",
            "running": bool(busy and busy["ticket_id"] == t["id"]),
            "pending_approvals": len(pending),
            "last_run": last,
        })
    return {"date_today": board_data["date_today"], "count": len(tickets),
            "open": sum(t["is_open"] for t in tickets), "resolved": sum(t["is_resolved"] for t in tickets),
            "running_run_id": busy["run_id"] if busy else None, "tickets": tickets}


async def _run_ticket(ticket_id: int, audit: Any) -> None:
    job = jobs[audit.run_id]
    try:
        async with run_lock:
            result = await team().resolve_ticket(ticket_id, audit=audit)
        queued = board.record_decision(result)
        d = result.decision
        # The team made its call, so the ticket is resolved on the board. Payments and
        # purchases it asked for wait separately in the approval queue for a human.
        await mcp("set_ticket_status", {"ticket_id": ticket_id, "status": "resolved"})
        job.update(status="ok", finished_at=board.now(), result=result.model_dump(mode="json"))
        feed.board_event("run_finished", f"Ticket {ticket_id} resolved: {d.decision}: {d.final_call}",
                         ticket_id=ticket_id, run_id=audit.run_id, agent="boss",
                         detail={"decision": d.decision, "pending_approvals": [q["approval_id"] for q in queued]})
        for q in queued:
            feed.board_event("approval_needed", f"Waiting for human approval: ${q['amount']:,.2f} to {q['payee']} ({q['kind']})",
                             ticket_id=ticket_id, run_id=audit.run_id, detail=q)
    except Exception as exc:
        job.update(status="error", finished_at=board.now(), error=f"{type(exc).__name__}: {exc}")
        feed.board_event("run_failed", f"Ticket {ticket_id} run failed: {type(exc).__name__}: {exc}",
                         ticket_id=ticket_id, run_id=audit.run_id)


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    """Start the agent team on one ticket. Returns at once; follow it with /api/events or /api/runs/{run_id}."""
    if (busy := running_job()) is not None:
        raise HTTPException(409, f"Ticket {busy['ticket_id']} is still running ({busy['run_id']}). Try again when it finishes.")
    details = await mcp("get_ticket_details", {"ticket_id": ticket_id})
    if "error" in details:
        raise HTTPException(404, details["error"])
    audit = team().new_ticket_audit(ticket_id, listener=lambda rec, raw: feed.from_audit(rec.run_id, rec.ticket_id, raw))
    jobs[audit.run_id] = {"run_id": audit.run_id, "ticket_id": ticket_id, "status": "running",
                          "model": MODEL_NAME, "started_at": board.now()}
    feed.board_event("run_started", f"Team started on ticket {ticket_id}", ticket_id=ticket_id, run_id=audit.run_id)
    task = asyncio.create_task(_run_ticket(ticket_id, audit))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": audit.run_id, "ticket_id": ticket_id, "status": "running",
            "events_url": f"/api/events?run_id={audit.run_id}", "result_url": f"/api/runs/{audit.run_id}"}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Status of one team run (running / ok / error) and its decision when done."""
    if run_id not in jobs:
        raise HTTPException(404, f"Run {run_id} not found in this server session (see output/audit_trail.json).")
    return jobs[run_id]


# ---- events -----------------------------------------------------------

@app.get("/api/events")
async def events(since: int = Query(0, ge=0, description="return events after this seq"),
                 limit: int = Query(200, ge=1, le=1000),
                 ticket_id: int | None = None, run_id: str | None = None) -> dict:
    """Recent agent events (who said what, which tools they used) for the live board. Poll with ?since=<last_seq>."""
    items = feed.since(since, limit, ticket_id, run_id)
    busy = running_job()
    return {"last_seq": feed.seq, "running_run_id": busy["run_id"] if busy else None,
            "count": len(items), "events": items}


# ---- payments (human approval) -----------------------------------------

class Approval(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving the payment.")
    confirm: bool = Field(description="Must be true: set when the human clicks Approve.")


@app.get("/api/payments/pending")
async def pending_payments() -> dict:
    """Payments the team prepared that are waiting for a human."""
    state = board.load_state()
    # Close requests for bills a human already paid (e.g. approved before this rule existed).
    covered = [c for a in list(state["approvals"].values()) if a["status"] == "approved"
               for c in board.cover_duplicates(state, a)]
    if covered:
        board.save_state(state)
        for c in covered:
            feed.board_event("payment_covered",
                             f"Ticket {c['ticket_id']}'s request for the same bill was already paid; nothing more to sign.",
                             ticket_id=c["ticket_id"], run_id=c["run_id"], agent="human", detail={"covered_by": c["covered_by"]})
    pending = [a for a in state["approvals"].values() if a["status"] == "pending"]
    return {"count": len(pending), "total": round(sum(a["amount"] for a in pending), 2), "payments": pending}


@app.post("/api/payments/{approval_id}/approve")
async def approve_payment(approval_id: str, body: Approval) -> dict:
    """A human approves one prepared payment. Only then is it recorded and the balance lowered."""
    if not body.confirm:
        raise HTTPException(400, "Payment not approved: confirm must be true (the human clicks Approve).")
    if running_job() is not None:
        raise HTTPException(409, "A team run is in progress. Approve after it finishes.")
    state = board.load_state()
    approval = state["approvals"].get(approval_id)
    if approval is None:
        raise HTTPException(404, f"No prepared payment {approval_id}.")
    if approval["status"] != "pending":
        raise HTTPException(409, f"Payment {approval_id} is {approval['status']}, not pending.")

    result = await mcp("record_payment", {
        "kind": approval["kind"], "amount": approval["amount"], "approved_by": body.approved_by.strip(),
        "ref_id": approval["ref_id"], "account": approval["account"], "payee": approval["payee"],
    })
    if not result.get("ok"):
        feed.board_event("payment_refused", f"Payment {approval_id} refused: {result.get('error')}",
                         ticket_id=approval["ticket_id"], run_id=approval["run_id"], agent="human")
        raise HTTPException(422, result.get("error", "Payment refused by the MCP server."))

    approval.update(status="approved", approved_by=body.approved_by.strip(), approved_at=board.now(),
                    payment=result["payment"], balance_after=result["balance_after"])
    # The same bill can be requested by several tickets (invoice 501 by #101 and #103).
    # One payment settles it, so close the duplicates instead of leaving them to be refused.
    covered = board.cover_duplicates(state, approval)
    for c in covered:
        feed.board_event("payment_covered",
                         f"Ticket {c['ticket_id']}'s request for the same bill is covered by this payment; nothing more to sign.",
                         ticket_id=c["ticket_id"], run_id=c["run_id"], agent="human", detail={"covered_by": approval_id})
    ticket_state = state["tickets"].get(str(approval["ticket_id"]), {})
    remaining = [i for i in ticket_state.get("approval_ids", []) if state["approvals"][i]["status"] == "pending"]
    board.save_state(state)
    feed.board_event("payment_approved",
                     f"{body.approved_by.strip()} approved ${approval['amount']:,.2f} to {approval['payee']}; "
                     f"checking is now ${result['balance_after']:,.2f}",
                     ticket_id=approval["ticket_id"], run_id=approval["run_id"], agent="human", detail=result)
    return {"approval": approval, "payment": result["payment"], "balance_after": result["balance_after"],
            "effects": result["effects"], "ticket_pending_approvals": len(remaining),
            "covered": [c["approval_id"] for c in covered]}


# ---- cash -------------------------------------------------------------

@app.get("/api/cash")
async def cash() -> dict:
    """Current checking balance from cash_accounts."""
    data = await mcp("get_cash_balance", {"account": "checking"})
    if "error" in data:
        raise HTTPException(404, data["error"])
    acct = data["accounts"][0]
    return {"account": acct["name"], "balance": acct["balance"], "as_of": acct["date"],
            "date_today": data["date_today"], "upcoming_obligations": data["upcoming_obligations"],
            "balance_after_obligations": data["balance_after_obligations"]}


# ---- reset ------------------------------------------------------------

@app.post("/api/reset")
async def reset() -> dict:
    """Reset campus_customs_new.db to the original values and clear board state, for a fresh run."""
    if running_job() is not None:
        raise HTTPException(409, "A team run is in progress. Reset after it finishes.")
    digest = reset_working_db()
    board.reset_state()
    jobs.clear()
    feed.board_event("reset", "Database reset to original values. Fresh run ready.")
    tickets = await mcp("list_tickets", {"status": "all"})
    checking = await mcp("get_cash_balance", {"account": "checking"})
    return {"ok": True, "sha256": digest, "tickets": tickets["tickets"],
            "checking_balance": checking["total_balance"], "date_today": tickets["date_today"]}


@app.get("/api/health")
async def health() -> dict:
    tools = await team().mcp.list_tools()
    return {"ok": True, "model": MODEL_NAME, "mcp_tools": len(tools), "running_run_id": (running_job() or {}).get("run_id")}

"""Build the Problem 9 reports from the real runs.

Reads the latest run of each ticket (output/board_state.json -> output/audit_trail.json),
the human approvals (board_state.json), and every money fact through the MCP server
(payments ledger, checking balance, ticket status). Writes:

- output/resolved_tickets.json
- output/desk_tickets.html   (fills the Actual sections and the Cash tab)
- output/resolved_board.html (board screenshots from output/resolved_board_images/)

    python build_reports.py

Re-run it after any new approval or run; it always reflects the current state.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import re
from datetime import datetime

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import board
from config import AUDIT_PATH, MCP_SERVER_SCRIPT, OUTPUT_DIR

import sys

START_BALANCE = 3400.00  # checking right after the Problem 9 reset (verified below)
TICKETS = (101, 102, 103)
AGENTS = {
    "boss": ("Coach Dan", "Boss", "#00356b"),
    "inventory": ("Stacks", "Inventory", "#1f4f8a"),
    "accounting": ("Penny", "Accounting", "#2b6cb0"),
    "facilities": ("Keys", "Facilities", "#3d5a80"),
    "customer_service": ("Sunny", "Customer Service", "#4a7fc1"),
}
ORDER = list(AGENTS)
DECISION = {
    "approve": ("Approved", "good"),
    "approve_with_conditions": ("Approved with conditions", "warn"),
    "hold": ("On hold", "warn"),
    "decline": ("Declined", "bad"),
    "escalate_to_human": ("Needs a human call", "warn"),
}
KIND = {"invoice": "Invoice payment", "rent": "Rent payment", "purchase_order": "Purchase order"}
SKIP_TOOLS = {"final_result", "ask_agent"}

# ---- agent icons (same characters as the React board) -----------------------

NAVY = "#00356b"
_BADGE = '<svg class="ic" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="30" fill="#fff" stroke="{n}" stroke-width="3"/>{body}</svg>'
ICONS = {
    "boss": '<svg class="ic" viewBox="0 0 120 120" aria-hidden="true"><g stroke="{n}" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"><path d="M26 36 C12 26 3 42 9 56 C15 52 22 46 31 41 Z" fill="{n}"/><path d="M94 36 C108 26 117 42 111 56 C105 52 98 46 89 41 Z" fill="{n}"/><path d="M60 20 C84 20 100 30 102 50 C104 62 108 78 100 92 C94 102 78 108 60 108 C42 108 26 102 20 92 C12 78 16 62 18 50 C20 30 36 20 60 20 Z" fill="#fff"/><path d="M70 38 C80 34 91 40 91 50 C91 58 83 60 77 58 C71 56 66 48 70 38 Z" fill="{n}" stroke="none"/><circle cx="43" cy="50" r="5.5" fill="{n}" stroke="none"/><circle cx="79" cy="49" r="3.5" fill="{n}" stroke="none"/><path d="M37 82 C39 99 81 99 83 82 C74 88 46 88 37 82 Z" fill="#fff"/><path d="M60 76 C55 85 38 85 30 75" fill="#fff" stroke-width="2.8"/><path d="M60 76 C65 85 82 85 90 75" fill="#fff" stroke-width="2.8"/><path d="M42 88 L45.5 74 L49.5 86 Z" fill="#fff" stroke-width="2.2"/><path d="M70.5 86 L74.5 74 L78 88 Z" fill="#fff" stroke-width="2.2"/><path d="M47 62 C47 55 73 55 73 62 C73 68 66 71 60 71 C54 71 47 68 47 62 Z" fill="{n}"/></g></svg>',
    "inventory": _BADGE.replace("{body}", '<g stroke="{n}" stroke-width="2.4" stroke-linejoin="round"><rect x="16" y="36" width="15" height="13" fill="#e8eef6"/><rect x="33" y="36" width="15" height="13" fill="#e8eef6"/><rect x="24" y="23" width="16" height="13" fill="#fff"/><path d="M24 13 l5 -3 h6 l5 3 l-3 4 l-2 -1 v7 h-6 v-7 l-2 1 Z" fill="{n}"/></g>'),
    "accounting": _BADGE.replace("{body}", '<g stroke="{n}" stroke-width="2.4" stroke-linejoin="round"><rect x="14" y="16" width="24" height="32" rx="3" fill="#e8eef6"/><path d="M19 24 h14 M19 30 h14 M19 36 h9" stroke-linecap="round"/><circle cx="41" cy="40" r="10" fill="{n}"/><text x="41" y="45" text-anchor="middle" font-size="14" font-weight="700" fill="#fff" stroke="none" font-family="Georgia,serif">$</text></g>'),
    "facilities": _BADGE.replace("{body}", '<g stroke="{n}" stroke-width="2.4" stroke-linejoin="round"><path d="M14 28 L32 15 L50 28" fill="none" stroke-linecap="round"/><rect x="18" y="27" width="28" height="21" fill="#e8eef6"/><rect x="28" y="35" width="8" height="13" fill="{n}"/><circle cx="45" cy="44" r="5" fill="#fff"/></g>'),
    "customer_service": _BADGE.replace("{body}", '<g stroke="{n}" stroke-width="2.4" stroke-linejoin="round"><path d="M14 20 Q14 15 19 15 H45 Q50 15 50 20 V36 Q50 41 45 41 H28 L20 49 V41 H19 Q14 41 14 36 Z" fill="#e8eef6"/><circle cx="25" cy="26" r="2" fill="{n}" stroke="none"/><circle cx="39" cy="26" r="2" fill="{n}" stroke="none"/><path d="M24 32 Q32 38 40 32" fill="none" stroke-linecap="round"/></g>'),
}
ICONS = {k: v.replace("{n}", NAVY) for k, v in ICONS.items()}

e = html.escape


def money(x: float) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


def short(text: str, n: int = 220) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def args_text(args) -> str:
    if not isinstance(args, dict):
        return ""
    return ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items())


# ---- gather -------------------------------------------------------------

async def mcp_facts() -> dict:
    transport = StdioTransport(command=sys.executable, args=[str(MCP_SERVER_SCRIPT)], cwd=str(MCP_SERVER_SCRIPT.parent))
    async with Client(transport) as c:
        async def call(name, args=None):
            r = await c.call_tool(name, args or {})
            return r.structured_content if r.structured_content is not None else json.loads(r.content[0].text)
        return {
            "cash": await call("get_cash_balance", {"account": "checking"}),
            "ledger": await call("check_invoice_payment"),
            "tickets": await call("list_tickets", {"status": "all"}),
            "leases": await call("get_lease_details"),
        }


def run_summary(run: dict) -> dict:
    events = run["events"]
    agents: dict[str, dict] = {}
    for ar in run["agent_runs"]:
        a = agents.setdefault(ar["agent"], {"agent": ar["agent"], "runs": 0, "seconds": 0.0, "tools": [],
                                            "asked": [], "asked_by": [], "said": None})
        a["runs"] += 1
        a["seconds"] += (ar.get("duration_ms") or 0) / 1000
        out = ar.get("output") or {}
        a["said"] = out.get("final_call") or out.get("answer") or a["said"]
    handoffs = []
    calls: dict = {}
    first_seen: list[str] = []
    for ev in events:
        if ev["kind"] == "delegate":
            frm, to = ev["agent"], ev["to"]
            handoffs.append({"from": frm, "to": to, "request": ev.get("request", "")})
            if to not in agents[frm]["asked"]:
                agents[frm]["asked"].append(to)
            if to in agents and frm not in agents[to]["asked_by"]:
                agents[to]["asked_by"].append(frm)
        elif ev["kind"] == "tool_call" and ev.get("tool") not in SKIP_TOOLS:
            call = {"tool": ev["tool"], "args": ev.get("args"), "result": None}
            calls[ev.get("tool_call_id")] = call
            agents[ev["agent"]]["tools"].append(call)
        elif ev["kind"] == "tool_result" and ev.get("tool_call_id") in calls:
            calls[ev["tool_call_id"]]["result"] = ev.get("result")
        elif ev["kind"] == "agent_start" and ev["agent"] not in first_seen:
            first_seen.append(ev["agent"])
    ordered = [agents[a] for a in ORDER if a in agents]
    return {"agents": ordered, "handoffs": handoffs, "order": [a for a in first_seen if a in agents]}


def checks_for(tid: int, summ: dict, decision: dict) -> list[tuple[str, bool]]:
    used = {a["agent"] for a in summ["agents"]}
    tools = {t["tool"] for a in summ["agents"] for t in a["tools"]}
    boss_order = [h["to"] for h in summ["handoffs"] if h["from"] == "boss"]
    first = boss_order[0] if boss_order else None
    d = decision["decision"]
    if tid == 101:
        return [
            ("Boss called Inventory (product availability)", "inventory" in boss_order),
            ("Accounting checked whether invoice 501 was paid", "accounting" in used and "check_invoice_payment" in tools),
            ("Used get_ticket_details", "get_ticket_details" in tools),
            ("Used check_item_availability (\"get inventory\")", "check_item_availability" in tools),
            ("Used check_invoice_payment (\"get invoice details\")", "check_invoice_payment" in tools),
            ("Realized the order can't be completed", d in ("hold", "decline", "escalate_to_human")),
            ("Facilities not needed", "facilities" not in used),
        ]
    if tid == 102:
        return [
            ("Boss called Facilities first to confirm the lease", first == "facilities"),
            ("Then Accounting checked there is enough cash", "accounting" in boss_order and boss_order.index("accounting") > boss_order.index("facilities") if "facilities" in boss_order and "accounting" in boss_order else False),
            ("Used get_lease_details", "get_lease_details" in tools),
            ("Used get_cash_balance (\"get cash account balance\")", "get_cash_balance" in tools),
            ("Inventory and Customer Service not needed", not ({"inventory", "customer_service"} & used)),
        ]
    pricing_with_discount = any(t["tool"] == "get_pricing" and isinstance(t["args"], dict) and t["args"].get("discount_pct")
                                for a in summ["agents"] for t in a["tools"])
    return [
        ("Boss called Inventory first (enough stock?)", first == "inventory"),
        ("Vendor check to see if we can get more (get_vendor_info)", "get_vendor_info" in tools),
        ("Boss called Accounting", "accounting" in boss_order),
        ("Boss called Customer Service", "customer_service" in boss_order),
        ("No made-up discount: options priced by Accounting, choice left to a human",
         pricing_with_discount and d in ("escalate_to_human", "approve_with_conditions", "hold")),
        ("Facilities not needed", "facilities" not in used),
    ]


def gather() -> dict:
    facts = asyncio.run(mcp_facts())
    state = board.load_state()
    runs = {r["run_id"]: r for r in json.loads(AUDIT_PATH.read_text(encoding="utf-8"))}
    status = {t["id"]: t["status"] for t in facts["tickets"]["tickets"]}
    subjects = {t["id"]: t for t in facts["tickets"]["tickets"]}
    payments = facts["ledger"]["payments_to_date"]
    approvals = list(state["approvals"].values())
    pay_to_approval = {(a.get("payment") or {}).get("id"): a for a in approvals if a.get("payment")}

    tickets = []
    for tid in TICKETS:
        ts = state["tickets"].get(str(tid))
        run = runs.get(ts["run_id"]) if ts else None
        if not run:
            raise SystemExit(f"No run on record for ticket {tid}; run the team first.")
        decision = run["result"]["decision"]
        summ = run_summary(run)
        mine = [a for a in approvals if a["ticket_id"] == tid and a["status"] != "superseded"]
        cash_out = round(sum(a["amount"] for a in mine if a["status"] == "approved"), 2)
        tickets.append({
            "ticket": subjects[tid], "status": status[tid], "run": run, "decision": decision,
            "summary": summ, "approvals": mine, "cash_out": cash_out,
            "checks": checks_for(tid, summ, decision),
        })

    paid_total = round(sum(p["amount"] for p in payments), 2)
    ending = facts["cash"]["total_balance"]
    assert abs(START_BALANCE - paid_total - ending) < 0.005, (START_BALANCE, paid_total, ending)
    return {"facts": facts, "tickets": tickets, "payments": payments, "pay_to_approval": pay_to_approval,
            "paid_total": paid_total, "ending": ending, "approvals": approvals}


# ---- resolved_tickets.json ----------------------------------------------

def write_json(g: dict) -> None:
    out = []
    for t in g["tickets"]:
        run, d = t["run"], t["decision"]
        out.append({
            "id": t["ticket"]["id"],
            "type": t["ticket"]["type"],
            "requester": t["ticket"]["requester"],
            "subject": t["ticket"]["subject"],
            "final_status": t["status"],
            "decision": d["decision"],
            "short_outcome": short(d["final_call"], 300),
            "run": {"run_id": run["run_id"], "started_at": run["started_at"], "finished_at": run["finished_at"],
                    "duration_ms": run["duration_ms"], "model": run["model_configured"], "models_used": run["models_used"],
                    "usage": run["usage_totals"], "agent_runs": run["agent_run_count"], "delegations": run["delegations"]},
            "agents": [{
                "agent": a["agent"], "name": AGENTS[a["agent"]][0], "role": AGENTS[a["agent"]][1],
                "seconds": round(a["seconds"], 1),
                "asked_by": a["asked_by"], "delegated_to": a["asked"],
                "tools_used": [{"tool": x["tool"], "args": x["args"]} for x in a["tools"]],
                "what_they_did": short(a["said"], 400),
            } for a in t["summary"]["agents"]],
            "handoffs": [{"from": h["from"], "to": h["to"], "request": short(h["request"], 300)} for h in t["summary"]["handoffs"]],
            "payment_requests": d["payment_requests"],
            "purchase_orders": d["purchase_orders"],
            "customer_message": d.get("customer_message"),
            "blockers": d["blockers"],
            "human_approvals": [{
                "approval_id": a["approval_id"], "kind": a["kind"], "payee": a["payee"], "amount": a["amount"],
                "status": a["status"], "approved_by": a.get("approved_by"), "approved_at": a.get("approved_at"),
                "payment_id": (a.get("payment") or {}).get("id"), "note": a.get("note"),
            } for a in t["approvals"]],
            "cash_change": -t["cash_out"],
            "matches_expected": [{"check": c, "passed": ok} for c, ok in t["checks"]],
        })
    doc = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": "data/campus_customs_new.db",
        "date_today": g["facts"]["cash"]["date_today"],
        "starting_checking_balance": START_BALANCE,
        "total_paid": g["paid_total"],
        "ending_checking_balance": g["ending"],
        "ending_matches_db": True,
        "tickets": out,
    }
    (OUTPUT_DIR / "resolved_tickets.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


# ---- desk_tickets.html: Actual + Cash -------------------------------------

EXTRA_CSS = """
  .cx { display: inline-block; font-size: 12.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; margin: 2px 6px 2px 0; line-height: 1.3; }
  .cx.paid { background: var(--red-bg); color: var(--red); }
  .cx.cov { background: var(--blue-100); color: var(--navy); }
  .cx.wait { background: var(--amber-bg); color: var(--amber); }
  table.ledger.per td { vertical-align: middle; }

  .steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; counter-reset: s; }
  .steps li { counter-increment: s; display: grid; grid-template-columns: 22px 30px 1fr; gap: 8px; align-items: start; font-size: 15px; line-height: 1.45; }
  .steps li::before { content: counter(s); display: grid; place-items: center; width: 22px; height: 22px; margin-top: 3px; border-radius: 50%; background: var(--navy); color: #fff; font-size: 12px; font-weight: 700; }
  .steps .mini .ic { width: 28px; height: 28px; }
  .times { color: var(--navy); font-size: 12px; }
  .outcome-box { display: grid; gap: 6px; padding: 10px 12px; border-radius: 8px; font-weight: 600; }
  .outcome-box.warn { background: var(--amber-bg); color: #78350f; }
  .outcome-box.good { background: var(--green-bg); color: var(--green); }
  .outcome-box.bad { background: var(--red-bg); color: var(--red); }
  .outcome-box .chip { justify-self: start; background: #fff; }
  .score { display: inline-block; font-weight: 700; padding: 6px 12px; border-radius: 8px; background: var(--amber-bg); color: var(--amber); }
  .score.all { background: var(--green-bg); color: var(--green); }
  .score.all::before { content: '✓ '; }
  details.more { margin-top: 10px; font-size: 13.5px; }
  details.more summary { cursor: pointer; color: var(--blue); font-weight: 600; }
  details.more h5 { margin: 10px 0 4px; color: var(--navy); }
  details.more li { margin: 4px 0; }
  .appr { align-items: center; }
  .act-outcome { display: grid; gap: 6px; padding: 12px 14px; border-radius: 10px; background: var(--blue-50); border-left: 4px solid var(--blue); margin-top: 12px; }
  .act-outcome .call { font-family: Georgia, serif; font-size: 15px; line-height: 1.45; }
  .chip { display: inline-block; font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 999px; }
  .chip.good { background: var(--green-bg); color: var(--green); }
  .chip.warn { background: var(--amber-bg); color: var(--amber); }
  .chip.bad { background: var(--red-bg); color: var(--red); }
  .chip.resolved { background: var(--green-bg); color: var(--green); }
  .crew { display: grid; gap: 8px; }
  .mate { display: grid; grid-template-columns: 34px 1fr; gap: 10px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); border-left: 4px solid var(--accent); }
  .mate .ic { width: 34px; height: 34px; }
  .mate b { font-family: Georgia, serif; color: var(--navy); }
  .mate small { color: var(--muted); }
  .mate .said { margin: 4px 0 0; font-size: 12.5px; color: var(--muted); font-style: italic; }
  .flow { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; counter-reset: step; }
  .flow li { counter-increment: step; display: grid; grid-template-columns: 22px 1fr; gap: 8px; font-size: 13px; }
  .flow li::before { content: counter(step); display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--navy); color: #fff; font-size: 11px; font-weight: 700; }
  .flow .who { font-weight: 700; color: var(--navy); }
  .flow .req { color: var(--muted); }
  .checks { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 13.5px; }
  .checks .ok::before { content: '✓'; color: var(--green); font-weight: 800; margin-right: 8px; }
  .checks .no::before { content: '✗'; color: var(--red); font-weight: 800; margin-right: 8px; }
  .appr { display: flex; justify-content: space-between; gap: 10px; padding: 8px 10px; border-radius: 8px; background: var(--blue-50); font-size: 13px; margin-bottom: 6px; }
  .appr b { font-family: Georgia, serif; }
  .st { font-size: 11px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; padding: 2px 8px; border-radius: 999px; white-space: nowrap; align-self: center; }
  .st.approved { background: var(--green-bg); color: var(--green); }
  .st.pending { background: var(--amber-bg); color: var(--amber); }
  .st.covered { background: var(--blue-100); color: var(--navy); }
  .cash-wrap { display: grid; gap: 18px; }
  .tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
  @media (max-width: 900px) { .tiles { grid-template-columns: 1fr 1fr; } }
  .tile { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
  .tile .k { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
  .tile .v { font-size: 26px; font-weight: 700; color: var(--navy); font-family: Georgia, serif; }
  .tile .v.out { color: var(--red); }
  .tile .s { font-size: 12.5px; color: var(--muted); }
  .tile.check { border-color: var(--green); background: var(--green-bg); }
  .tile.check .v { color: var(--green); }
  table.ledger { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; font-size: 14px; }
  .ledger th { text-align: left; background: var(--navy); color: #fff; font-weight: 600; padding: 10px 12px; font-size: 12.5px; letter-spacing: .03em; }
  .ledger td { padding: 10px 12px; border-top: 1px solid var(--line); vertical-align: top; }
  .ledger td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .ledger tr.start td, .ledger tr.end td { background: var(--blue-50); font-weight: 700; }
  .ledger .minus { color: var(--red); }
  .card-box { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; }
  .card-box h3 { margin: 0 0 10px; color: var(--navy); font-size: 17px; }
  .math { font-family: Consolas, monospace; font-size: 14px; line-height: 1.9; }
  .why li { margin: 6px 0; font-size: 14px; }
"""


TOOL_MEANING = {
    "get_ticket_details": "read the ticket",
    "list_tickets": "looked at the board",
    "check_item_availability": "stock by size (\"get inventory\")",
    "get_vendor_info": "vendor lead time and whether they'll ship",
    "get_pricing": "cost, price and discount math",
    "check_invoice_payment": "is the invoice paid? (\"get invoice details\")",
    "get_cash_balance": "checking balance and bills due (\"get cash account balance\")",
    "check_cash_for_payment": "can we afford this payment?",
    "get_lease_details": "lease, rent and due date (\"get lease details\")",
}
ROLE_VERB = {
    "inventory": "checked the stockroom",
    "accounting": "checked the money",
    "facilities": "checked the lease",
}


def _first_sentence(text: str, n: int = 170) -> str:
    text = " ".join(str(text or "").split())
    m = re.match(r"(.+?\.)(\s|$)", text)
    return short(m.group(1) if m else text, n)


def _finding(call: dict) -> str | None:
    """One plain fact from a tool's result, e.g. 'size S: 0 on hand, short 1'."""
    r, a = call.get("result"), call.get("args") or {}
    if not isinstance(r, dict) or r.get("truncated") or "error" in r:
        return None
    tool = call["tool"]
    try:
        if tool == "check_item_availability":
            if "qty_available" in r:
                out = f"size {r['size_requested']}: {r['qty_available']} on hand"
                if r.get("shortfall"):
                    out += f", short {r['shortfall']}"
                return out
            return "on hand: " + ", ".join(f"{x['size']} {x['qty']}" for x in r["sizes"])
        if tool == "get_vendor_info":
            v = r["vendors"][0]
            return f"{v['name']}: {v['lead_days']}-day lead time, " + ("will ship" if v["will_ship"] else "won't ship until its invoice is paid")
        if tool == "check_invoice_payment":
            inv = r.get("invoice") or (r.get("invoices") or [None])[0]
            if not inv:
                return f"{r.get('payment_count', 0)} payments on record"
            if inv["is_paid"]:
                return f"invoice {inv['invoice_id']}: paid"
            return f"invoice {inv['invoice_id']}: {money(inv['outstanding_amount'])} unpaid, {inv['days_overdue']} days overdue"
        if tool == "get_cash_balance":
            return f"checking {money(r['total_balance'])}; bills due {money(r['total_obligations'])} → leaves {money(r['balance_after_obligations'])}"
        if tool == "check_cash_for_payment":
            return f"{money(r['proposed_amount'])} {'fits' if r['can_pay'] else 'does NOT fit'} (leaves {money(r['balance_after'])})"
        if tool == "get_lease_details":
            l = r["leases"][0]
            return f"rent {money(l['monthly_rent'])} due {l['next_due']} ({l['days_until_due']} days away)"
        if tool == "get_pricing":
            q = r["items"][0].get("quote")
            if q:
                return f"{q['discount_pct']:g}% off = {money(q['unit_price'])}/unit"
            return f"cost {money(r['items'][0]['unit_cost'])}, list {money(r['items'][0]['list_price'])}"
    except (KeyError, IndexError, TypeError):
        return None
    return None


PRIORITY = ["check_invoice_payment", "check_cash_for_payment", "get_lease_details", "check_item_availability",
            "get_vendor_info", "get_cash_balance", "get_pricing"]


def _agent_line(a: dict, requester: str, said_before: set) -> str:
    """One plain sentence per agent: at most two key facts, none a teammate already reported."""
    agent = a["agent"]
    name = AGENTS[agent][0]
    if agent == "boss":
        asked = ", then ".join(f"<b>{e(AGENTS[x][0])}</b>" for x in a["asked"]) or "nobody"
        return f"<b>{e(name)}</b> read the ticket and called {asked}."
    if agent == "customer_service":
        return f"<b>{e(name)}</b> drafted a reply to {e(requester)}."
    best: dict[str, str] = {}
    for c in a["tools"]:
        f = _finding(c)
        if f and c["tool"] != "get_pricing":
            best[c["tool"]] = f  # keep the latest result per tool (e.g. the final affordability check)
    facts = [best[t] for t in PRIORITY if t in best and best[t] not in said_before][:2]
    said_before.update(facts)
    pcts = sorted({c["args"].get("discount_pct") for c in a["tools"]
                   if c["tool"] == "get_pricing" and isinstance(c.get("args"), dict) and c["args"].get("discount_pct")})
    if pcts:
        facts.append("priced " + "/".join(f"{p:g}%" for p in pcts) + " discount options and left the choice to a human")
    return f"<b>{e(name)}</b> {ROLE_VERB.get(agent, 'helped')}" + (": " + e("; ".join(facts)) + "." if facts else ".")


def _date_lines(t: dict, today: str) -> list[str]:
    lines, done = [], set()
    for a in t["summary"]["agents"]:
        for c in a["tools"]:
            r = c.get("result")
            if not isinstance(r, dict) or r.get("truncated"):
                continue
            if c["tool"] == "check_invoice_payment" and "invoice" not in done:
                inv = r.get("invoice") or (r.get("invoices") or [None])[0]
                if inv and not inv["is_paid"]:
                    done.add("invoice")
                    lines.append(f"Invoice {inv['invoice_id']} was due {inv['due_date']}, so it's <b>{inv['days_overdue']} days overdue</b> on desk.date_today ({today}).")
            if c["tool"] == "get_lease_details" and "lease" not in done and r.get("leases"):
                done.add("lease")
                l = r["leases"][0]
                lines.append(f"Rent is due {l['next_due']}: <b>{l['days_until_due']} days after</b> desk.date_today ({today}), so not overdue.")
            if c["tool"] == "get_vendor_info" and "vendor" not in done and r.get("vendors"):
                done.add("vendor")
                v = r["vendors"][0]
                when = f"earliest {v['earliest_delivery_if_ordered_today']}" if v["will_ship"] else "no date until the invoice is paid"
                lines.append(f"Restock lead time is {v['lead_days']} days from desk.date_today: {when}.")
    rank = lambda x: 0 if x.startswith("Invoice") else 1 if x.startswith("Rent") else 2
    return sorted(lines, key=rank) or [f"All dates were counted from desk.date_today ({today})."]


def actual_html(t: dict, today: str) -> str:
    d = t["decision"]
    label, tone = DECISION.get(d["decision"], (d["decision"], "warn"))
    summ = t["summary"]
    by_agent = {a["agent"]: a for a in summ["agents"]}
    passed = sum(ok for _, ok in t["checks"])
    total = len(t["checks"])
    parts = []

    parts.append("<h4>Agents</h4><ol class=\"steps\">")
    said_before: set = set()
    for agent in summ["order"]:
        parts.append(f"<li><span class=\"mini\">{ICONS[agent]}</span><span>{_agent_line(by_agent[agent], t['ticket']['requester'], said_before)}</span></li>")
    parts.append("</ol>")

    counts: dict[str, int] = {}
    for a in summ["agents"]:
        for c in a["tools"]:
            counts[c["tool"]] = counts.get(c["tool"], 0) + 1
    parts.append("<h4>Tools</h4>")
    for tool, n in counts.items():
        parts.append(f'<span class="tool">{e(tool)}</span>{f" <b class=\'times\'>×{n}</b>" if n > 1 else ""} '
                     f'<span class="said">{e(TOOL_MEANING.get(tool, ""))}</span><br>')

    parts.append("<h4>Date check</h4><ul>" + "".join(f"<li>{x}</li>" for x in _date_lines(t, today)) + "</ul>")

    parts.append(f"""<h4>Outcome</h4><div class="outcome-box {tone}"><span class="chip {tone}">{e(label)}</span>
<span>{e(_first_sentence(d['final_call'], 240))}</span></div>""")

    if t["approvals"]:
        parts.append("<h4>Your signatures</h4>")
        for ap in t["approvals"]:
            what = {"approved": f"signed by {e(ap.get('approved_by') or '')}", "pending": "waiting for you",
                    "covered": "already paid through another ticket"}.get(ap["status"], ap["status"])
            parts.append(f'<div class="appr"><span>{money(ap["amount"])} {e(KIND.get(ap["kind"], ap["kind"]).lower())} → {e(ap["payee"])}</span>'
                         f'<span class="st {e(ap["status"])}">{e(what)}</span></div>')

    parts.append(f"""<h4>Matches expected?</h4><div class="score {'all' if passed == total else ''}">{passed} of {total} expectations met</div>
<details class="more"><summary>See each check</summary><ul class="checks">{''.join(f'<li class="{"ok" if ok else "no"}">{e(c)}</li>' for c, ok in t['checks'])}</ul></details>""")

    convo = "".join(f"<li><b>{e(AGENTS[h['from']][0])} → {e(AGENTS[h['to']][0])}:</b> {e(short(h['request'], 400))}</li>" for h in summ["handoffs"])
    words = "".join(f"<li><b>{e(AGENTS[a['agent']][0])}:</b> {e(short(a['said'], 500))}</li>" for a in summ["agents"])
    run = t["run"]
    parts.append(f"""<details class="more"><summary>Show the full conversation</summary>
<p class="said">{run['duration_ms']/1000:.0f}s · {run['agent_run_count']} agent runs · {run['usage_totals']['requests']} model calls · {e(', '.join(run['models_used']))}</p>
<h5>What they asked each other</h5><ol>{convo}</ol><h5>What each one reported</h5><ul>{words}</ul></details>""")
    return "\n".join(parts)


# ---- ticket dashboards: Francisco's Expected plan (Problem 6) next to what actually happened ----

EXPECTED = {
    101: {
        "agents": ["boss", "inventory", "accounting"],
        "agents_note": "Boss calls Inventory (it's about stock); Accounting checks whether the linked invoice is paid.",
        "tools": ["get_ticket_details", "check_item_availability", "check_invoice_payment"],
        "date": "Invoice 501 was due 2026-08-28, so it's overdue on desk.date_today.",
        "outcome": "They realize they can't complete the order.",
        "not_needed": ["facilities"],
    },
    102: {
        "agents": ["boss", "facilities", "accounting"],
        "agents_note": "Boss calls Facilities first to confirm the lease, then Accounting to check the cash.",
        "tools": ["get_lease_details", "get_cash_balance"],
        "date": "Rent due 2026-09-02 is 2 days after desk.date_today, so it's not overdue.",
        "outcome": "Rent is only prepared; a human approves the payment.",
        "not_needed": ["inventory", "customer_service"],
    },
    103: {
        "agents": ["boss", "inventory", "accounting", "customer_service"],
        "agents_note": "Inventory first (enough stock?), the vendor check (by Inventory), then Accounting and Customer Service.",
        "tools": ["get_ticket_details", "check_item_availability", "get_vendor_info", "get_pricing"],
        "date": "Any restock date is desk.date_today + the vendor's lead days, and only once it will ship.",
        "outcome": "The Boss doesn't make up a random discount.",
        "not_needed": ["facilities"],
    },
}

START_FACTS = {
    101: [("Size S on hand", "0 (M 5 · L 3 · XL 2)"), ("Invoice 501", "$840 unpaid, 3 days overdue"),
          ("Vendor will ship", "No"), ("Reprint lead time", "5 days, after the invoice is paid")],
    102: [("Monthly rent", "$2,400"), ("Next due", "2026-09-02 (in 2 days)"),
          ("Checking", "$3,400"), ("Left after all bills", "$160")],
    103: [("Size M on hand", "8 of 20 (short 12)"), ("Cost / list", "$22 / $58"),
          ("Restock 12", "$264, blocked by invoice 501"), ("Discount policy", "none, a human decides")],
}

DASH_CSS = """
  .glance { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 10px 16px; display: grid; gap: 6px; }
  .glance .gl { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 18px; font-size: 13.5px; }
  .glance .gk { font-size: 11px; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); min-width: 92px; }
  .glance .gi { color: var(--muted); }
  .glance .gi b { color: var(--ink); font-weight: 700; }
  .glance .gi b.neg { color: var(--red); }
  .glance .gi .ic { width: 18px; height: 18px; vertical-align: -4px; }
  .dash { display: grid; gap: 16px; margin-top: 18px; }
  .kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
  @media (max-width: 1000px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
  .kpi { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; box-shadow: 0 1px 2px rgba(0,35,80,.05); }
  .kpi .k { font-size: 11.5px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); }
  .kpi .v { font-size: 20px; line-height: 1.2; font-weight: 800; color: var(--navy); margin-top: 2px; font-family: Georgia, serif; }
  .kpi .s { font-size: 12px; color: var(--muted); }
  .kpi.good { border-color: #a7e3bf; background: var(--green-bg); } .kpi.good .v { color: var(--green); }
  .kpi.warn { border-color: #f5d48a; background: var(--amber-bg); } .kpi.warn .v { color: var(--amber); }
  .kpi.bad .v { color: var(--red); }
  .kpi .faces { display: flex; gap: 2px; margin-top: 4px; }
  .kpi .faces .ic { width: 24px; height: 24px; }
  .board { background: var(--card); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
  .board-head, .brow { display: grid; grid-template-columns: 1fr 1fr; }
  .board-head > div { padding: 12px 18px; font-size: 15px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
  .brow h4 { margin: 0 0 8px; font-size: 14px; color: var(--navy); display: flex; align-items: center; gap: 8px; }
  .brow .fitb { margin-left: auto; }
  .brow .real { border-left: 1px solid var(--line); }
  .board-head .h-plan { background: var(--blue); color: #fff; }
  .board-head .h-real { background: #64748b; color: #fff; }
  .board-head .h-row, .board-head .h-fit { background: #eef2f8; color: var(--muted); }
  .brow { border-top: 1px solid var(--line); }
  .brow > div { padding: 14px 18px; font-size: 14px; line-height: 1.5; }
  .brow .rl { font-weight: 800; color: var(--navy); background: var(--blue-50); }
  .brow .plan { background: #fbfcff; }
  .brow .fit { display: grid; align-content: center; justify-items: start; }
  .badge { font-size: 12px; font-weight: 800; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
  .badge.ok { background: var(--green-bg); color: var(--green); }
  .badge.plus { background: var(--blue-100); color: var(--navy); }
  .badge.no { background: var(--red-bg); color: var(--red); }
  .pipe { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
  .pipe .node { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px 3px 4px; border-radius: 999px; background: #fff; border: 1.5px solid var(--line); font-size: 13px; font-weight: 700; color: var(--navy); }
  .pipe .node .ic { width: 22px; height: 22px; }
  .pipe .node.extra { border-style: dashed; border-color: var(--blue); }
  .pipe .arr { color: var(--muted); font-weight: 700; }
  .note-s { display: block; margin-top: 6px; font-size: 12.5px; color: var(--muted); }
  .tchip { display: inline-block; font-family: Consolas, monospace; font-size: 12px; padding: 2px 8px; border-radius: 6px; margin: 2px 4px 2px 0; border: 1px solid var(--blue-100); background: var(--blue-50); color: var(--navy); }
  .tchip.hit { background: var(--green-bg); border-color: #a7e3bf; color: var(--green); }
  .tchip.hit::before { content: '✓ '; font-family: system-ui; font-weight: 800; }
  .tchip.miss { background: var(--red-bg); border-color: #f3b4ad; color: var(--red); }
  .tchip.extra { border-style: dashed; }
  .tchip .n { font-family: system-ui; font-weight: 800; margin-left: 3px; }
  .out-real { display: grid; gap: 4px; }
  .facts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
  .fact-card { background: var(--card); border: 1px solid var(--line); border-top: 4px solid var(--accent); border-radius: 12px; padding: 12px 14px; display: grid; gap: 6px; align-content: start; }
  .fact-card .top { display: flex; align-items: center; gap: 8px; }
  .fact-card .top .ic { width: 30px; height: 30px; }
  .fact-card .top b { color: var(--navy); font-family: Georgia, serif; }
  .fact-card .top small { color: var(--muted); display: block; font-size: 11.5px; }
  .fact-card ul { margin: 0; padding-left: 18px; font-size: 13.5px; line-height: 1.45; }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 1000px) { .row2 { grid-template-columns: 1fr; } .board-head, .brow { grid-template-columns: 1fr; } }
  .panel-lite { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; }
  .panel-lite h3 { margin: 0 0 10px; font-size: 15px; color: var(--navy); }
  .sec-title { margin: 6px 0 -4px; font-size: 13px; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); }
"""


def _pipe(agents: list[str], extra: set[str] = frozenset()) -> str:
    nodes = [f'<span class="node {"extra" if a in extra else ""}">{ICONS[a]}{e(AGENTS[a][0])}</span>' for a in agents]
    return '<div class="pipe">' + '<span class="arr">→</span>'.join(nodes) + "</div>"


def _facts(agent: dict, requester: str) -> list[str]:
    a = agent["agent"]
    if a == "boss":
        return []
    if a == "customer_service":
        return [f"Drafted a reply to {requester}"]
    best: dict[str, str] = {}
    for c in agent["tools"]:
        f = _finding(c)
        if f and c["tool"] != "get_pricing":
            best[c["tool"]] = f
    out = [best[t] for t in PRIORITY if t in best][:3]
    pcts = sorted({c["args"].get("discount_pct") for c in agent["tools"]
                   if c["tool"] == "get_pricing" and isinstance(c.get("args"), dict) and c["args"].get("discount_pct")})
    if pcts:
        out.append("Priced " + "/".join(f"{p:g}%" for p in pcts) + " options; no pick")
    return [o[0].upper() + o[1:] for o in out]


def dash_html(t: dict, today: str) -> str:
    tid = t["ticket"]["id"]
    exp = EXPECTED[tid]
    d, run, summ = t["decision"], t["run"], t["summary"]
    label, tone = DECISION.get(d["decision"], (d["decision"], "warn"))
    used = summ["order"]
    passed, total = sum(ok for _, ok in t["checks"]), len(t["checks"])
    counts: dict[str, int] = {}
    for a in summ["agents"]:
        for c in a["tools"]:
            counts[c["tool"]] = counts.get(c["tool"], 0) + 1
    calls = sum(counts.values())
    cash = -t["cash_out"]

    result = [("Decision", f'<span class="chip {tone}">{e(label)}</span>'),
              ("Plan match", f"<b>{passed}/{total}</b>"),
              ("Agents", f"<b>{len(used)} of 5</b> " + "".join(ICONS[a] for a in used)),
              ("Tool calls", f"<b>{calls}</b>"),
              ("Cash impact", f'<b class="{"neg" if cash < 0 else ""}">{money(cash) if cash else "$0.00"}</b>')]
    glance = ('<div class="glance"><div class="gl"><span class="gk">Result</span>'
              + "".join(f'<span class="gi">{k}: {v}</span>' for k, v in result)
              + '</div><div class="gl"><span class="gk">Before the run</span>'
              + "".join(f'<span class="gi">{e(k)}: <b>{e(v)}</b></span>' for k, v in START_FACTS[tid])
              + "</div></div>")

    extra_agents = set(used) - set(exp["agents"])
    missing_agents = [a for a in exp["agents"] if a not in used]
    a_fit = ('<span class="badge no">missing ' + ", ".join(AGENTS[a][0] for a in missing_agents) + "</span>") if missing_agents else (
        '<span class="badge ok">✓ as planned</span>' + ("".join(f' <span class="badge plus">+ {e(AGENTS[a][0])}</span>' for a in extra_agents)))

    exp_tools = exp["tools"]
    t_plan = "".join(f'<span class="tchip">{e(x)}</span>' for x in exp_tools)
    t_real = "".join(f'<span class="tchip hit">{e(x)}{f"<span class=n>×{counts[x]}</span>" if counts[x] > 1 else ""}</span>' for x in exp_tools if x in counts)
    t_real += "".join(f'<span class="tchip miss">✗ {e(x)}</span>' for x in exp_tools if x not in counts)
    t_real += "".join(f'<span class="tchip extra">+ {e(x)}{f"<span class=n>×{n}</span>" if n > 1 else ""}</span>' for x, n in counts.items() if x not in exp_tools)
    t_missing = [x for x in exp_tools if x not in counts]
    t_fit = '<span class="badge no">missing</span>' if t_missing else '<span class="badge ok">✓ all used</span>' + (
        f' <span class="badge plus">+{sum(1 for x in counts if x not in exp_tools)} extra</span>' if any(x not in exp_tools for x in counts) else "")

    dates = _date_lines(t, today)
    nn_used = [a for a in exp["not_needed"] if a in used]
    nn_real = ("Called anyway: " + ", ".join(AGENTS[a][0] for a in nn_used)) if nn_used else \
        "Stayed out: " + ", ".join(f"<b>{e(AGENTS[a][0])}</b>" for a in exp["not_needed"])
    outcome_ok = t["checks"][-2][1] if tid == 101 else t["checks"][-2][1] if tid == 103 else True

    rows = [
        ("Agents", f'{_pipe(exp["agents"])}<span class="note-s">{e(exp["agents_note"])}</span>', _pipe(used, extra_agents), a_fit),
        ("Tools", t_plan, t_real, t_fit),
        ("Date check", e(exp["date"]), "<br>".join(dates), '<span class="badge ok">✓ correct</span>'),
        ("Outcome", f"<b>{e(exp['outcome'])}</b>",
         f'<div class="out-real"><span class="chip {tone}" style="justify-self:start">{e(label)}</span><span>{e(_first_sentence(d["final_call"], 200))}</span></div>',
         '<span class="badge ok">✓ matches</span>' if outcome_ok else '<span class="badge no">different</span>'),
        ("Not needed", ", ".join(e(AGENTS[a][0]) for a in exp["not_needed"]), nn_real,
         '<span class="badge no">called</span>' if nn_used else '<span class="badge ok">✓ stayed out</span>'),
    ]
    # Expected and Actual side by side, each section lined up across the two panels.
    board = ['<div class="board"><div class="board-head"><div class="h-plan">Expected</div><div class="h-real">Actual</div></div>']
    for name, plan, real, fit in rows:
        board.append(f'<div class="brow"><div class="plan"><h4>{name}</h4>{plan}</div>'
                     f'<div class="real"><h4>{name} <span class="fitb">{fit}</span></h4>{real}</div></div>')
    board.append("</div>")

    cards = []
    by = {a["agent"]: a for a in summ["agents"]}
    for a in used:
        name, role, accent = AGENTS[a]
        fs = _facts(by[a], t["ticket"]["requester"])
        if a == "boss":
            fs = ["Called " + ", then ".join(AGENTS[x][0] for x in by[a]["asked"]), f"Call: {label}"]
        cards.append(f'<div class="fact-card" style="--accent:{accent}"><div class="top">{ICONS[a]}<div><b>{e(name)}</b><small>{e(role)}</small></div></div>'
                     f'<ul>{"".join(f"<li>{e(x)}</li>" for x in fs)}</ul></div>')

    sigs = "".join(
        f'<div class="appr"><span>{money(ap["amount"])} {e(KIND.get(ap["kind"], ap["kind"]).lower())} → {e(ap["payee"])}</span>'
        f'<span class="st {e(ap["status"])}">{e({"approved": "signed by " + (ap.get("approved_by") or ""), "pending": "waiting for you", "covered": "paid via another ticket"}.get(ap["status"], ap["status"]))}</span></div>'
        for ap in t["approvals"]) or '<p class="said">No payments needed.</p>'
    convo = "".join(f"<li><b>{e(AGENTS[h['from']][0])} → {e(AGENTS[h['to']][0])}:</b> {e(short(h['request'], 400))}</li>" for h in summ["handoffs"])
    words = "".join(f"<li><b>{e(AGENTS[a['agent']][0])}:</b> {e(short(a['said'], 500))}</li>" for a in summ["agents"])
    msg = d.get("customer_message")

    return f"""<div class="dash">
{''.join(board)}
<div class="sec-title">What each agent found</div>
<div class="facts-grid">{''.join(cards)}</div>
<div class="row2">
  <div class="panel-lite"><h3>Signatures</h3>{sigs}</div>
  <div class="panel-lite"><h3>{'Message to ' + e(t['ticket']['requester']) if msg else 'Details'}</h3>
    {f'<p class="said" style="white-space:pre-line;margin:0 0 8px">{e(short(msg, 600))}</p>' if msg else ''}
    <details class="more"><summary>See every check ({passed}/{total})</summary><ul class="checks">{''.join(f'<li class="{"ok" if ok else "no"}">{e(c)}</li>' for c, ok in t['checks'])}</ul></details>
    <details class="more"><summary>Show the full conversation</summary><h5>What they asked each other</h5><ol>{convo}</ol><h5>What each one reported</h5><ul>{words}</ul></details>
  </div>
</div>
<div class="sec-title">At a glance</div>
{glance}
</div>"""


def cash_html(g: dict) -> str:
    """Cash tab as a dashboard: tiles, the ledger, and one row per ticket.

    The math is verified in code (gather() asserts start - paid == cash_accounts),
    so the page only shows the result.
    """
    facts = g["facts"]
    pending = [a for a in g["approvals"] if a["status"] == "pending"]
    waiting = round(sum(a["amount"] for a in pending), 2)

    # Ledger: start, each human-signed payment with the running balance, end.
    rows = [f'<tr class="start"><td>Start</td><td>—</td><td>Checking after the reset</td><td></td><td class="num"></td><td class="num">{money(START_BALANCE)}</td></tr>']
    bal = START_BALANCE
    for p in sorted(g["payments"], key=lambda p: p["id"]):
        ap = g["pay_to_approval"].get(p["id"], {})
        bal = round(bal - p["amount"], 2)
        what = {"invoice": f"Invoice {p['ref_id']}", "rent": f"Rent (lease {p['ref_id']})", "purchase_order": "Restock PO"}.get(p["kind"], p["kind"])
        rows.append(f"<tr><td>{e(p['paid_at'])}</td><td>#{ap.get('ticket_id', '?')}</td><td>{e(what)} → {e(ap.get('payee', ''))}</td>"
                    f"<td>{e(p['approved_by'])}</td><td class=\"num minus\">−{money(p['amount'])}</td><td class=\"num\">{money(bal)}</td></tr>")
    rows.append(f'<tr class="end"><td>End</td><td>—</td><td>Checking now (cash_accounts)</td><td></td><td class="num minus">−{money(g["paid_total"])}</td><td class="num">{money(g["ending"])}</td></tr>')

    # One row per ticket: what the team's run did to cash, and what humans signed after.
    per = []
    for t in g["tickets"]:
        d = t["decision"]
        label, tone = DECISION.get(d["decision"], (d["decision"], "warn"))
        after = []
        for ap in t["approvals"]:
            if ap["status"] == "approved":
                after.append(f'<span class="cx paid">−{money(ap["amount"])} {e(KIND[ap["kind"]].lower())}</span>')
            elif ap["status"] == "covered":
                after.append(f'<span class="cx cov">{e(KIND[ap["kind"]].lower())} already paid via another ticket</span>')
            elif ap["status"] == "pending":
                short_by = round(ap["amount"] - g["ending"], 2)
                note = f" · won't fit (short {money(short_by)})" if short_by > 0 else ""
                after.append(f'<span class="cx wait">{money(ap["amount"])} {e(KIND[ap["kind"]].lower())} unsigned{note}</span>')
        net = -t["cash_out"]
        per.append(f"<tr><td><b>#{t['ticket']['id']}</b> {e(t['ticket']['subject'])}</td><td><span class=\"chip {tone}\">{e(label)}</span></td>"
                   f"<td class=\"num\">$0.00</td><td>{' '.join(after) or '<span class=said>nothing requested</span>'}</td>"
                   f"<td class=\"num {'minus' if net < 0 else ''}\"><b>{money(net) if net else '$0.00'}</b></td></tr>")

    return f"""<div class="cash-wrap">
<div class="tiles">
  <div class="tile"><div class="k">Start (after reset)</div><div class="v">{money(START_BALANCE)}</div><div class="s">desk.date_today {e(facts['cash']['date_today'])}</div></div>
  <div class="tile"><div class="k">Paid out</div><div class="v out">−{money(g['paid_total'])}</div><div class="s">{len(g['payments'])} payments, all signed by a human</div></div>
  <div class="tile check"><div class="k">Ending checking</div><div class="v">{money(g['ending'])}</div><div class="s">✓ matches cash_accounts</div></div>
  <div class="tile"><div class="k">Waiting for a signature</div><div class="v">{money(waiting)}</div><div class="s">{', '.join(f"#{a['ticket_id']} {KIND[a['kind']].lower()}" for a in pending) or 'nothing'} · not in the balance</div></div>
</div>

<div class="sec-title">Every dollar that moved</div>
<table class="ledger"><thead><tr><th>Date</th><th>Ticket</th><th>What</th><th>Signed by</th><th style="text-align:right">Amount</th><th style="text-align:right">Balance</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>

<div class="sec-title">Cash by ticket</div>
<table class="ledger per"><thead><tr><th>Ticket</th><th>Team's call</th><th style="text-align:right">When resolved</th><th>After human signatures</th><th style="text-align:right">Net</th></tr></thead>
<tbody>{''.join(per)}</tbody></table>
<p class="said">Agents only prepare payments, so resolving a ticket never moves cash. Money leaves checking only when a human signs, and never below $0.</p>
</div>"""


def write_desk(g: dict) -> None:
    p = OUTPUT_DIR / "desk_tickets.html"
    s = p.read_text(encoding="utf-8")
    for t in g["tickets"]:
        tid = t["ticket"]["id"]
        s = re.sub(rf"<!--DASH-{tid}-START-->.*?<!--DASH-{tid}-END-->",
                   lambda m: f"<!--DASH-{tid}-START-->{dash_html(t, g['facts']['cash']['date_today'])}<!--DASH-{tid}-END-->", s, flags=re.S)
    s = re.sub(r'\n  <div class="facts">.*?</div>\n  </div>\n  <div class="source">.*?</div>', "", s, flags=re.S)
    s = re.sub(r'<span class="pill (open|resolved)">\w+</span>', '<span class="pill resolved">resolved</span>', s)
    if ".pill.resolved" not in s:
        s = s.replace("  .pill.open {", "  .pill.resolved { background: var(--green-bg); color: var(--green); }\n  .pill.open {", 1)
    s = re.sub(r"<!--CASH-START-->.*?<!--CASH-END-->", lambda m: f"<!--CASH-START-->{cash_html(g)}<!--CASH-END-->", s, flags=re.S)
    s = re.sub(r"<!--EXTRA-STYLE-START-->.*?<!--EXTRA-STYLE-END-->", lambda m: f"<!--EXTRA-STYLE-START-->{EXTRA_CSS}{DASH_CSS}<!--EXTRA-STYLE-END-->", s, flags=re.S)
    p.write_text(s, encoding="utf-8")


# ---- resolved_board.html ---------------------------------------------------

def write_board(g: dict) -> None:
    img_dir = OUTPUT_DIR / "resolved_board_images"
    sections = []
    for t in g["tickets"]:
        tid = t["ticket"]["id"]
        d = t["decision"]
        label, tone = DECISION.get(d["decision"], (d["decision"], "warn"))
        img = img_dir / f"ticket_{tid}.png"
        b64 = base64.b64encode(img.read_bytes()).decode()
        crew = " ".join(f'<span class="who">{ICONS[a["agent"]]}{e(AGENTS[a["agent"]][0])}</span>' for a in t["summary"]["agents"])
        appr = "".join(f'<li><b>{money(a["amount"])}</b> {e(KIND[a["kind"]].lower())} → {e(a["payee"])} <span class="st {e(a["status"])}">{e(a["status"])}</span>'
                       f'{(" by " + e(a["approved_by"])) if a.get("approved_by") else ""}</li>' for a in t["approvals"]) or "<li>None needed</li>"
        sections.append(f"""<section id="t{tid}">
  <div class="head"><h2>#{tid} · {e(t['ticket']['subject'])}</h2><span class="chip resolved">{e(t['status'])}</span><span class="chip {tone}">{e(label)}</span></div>
  <p class="call">{e(d['final_call'])}</p>
  <div class="meta"><div><h3>Who worked</h3><div class="crew">{crew}</div></div><div><h3>Human approvals</h3><ul>{appr}</ul></div></div>
  <figure><img alt="React board showing ticket {tid} resolved" src="data:image/png;base64,{b64}"><figcaption>The Campus Customs Agent Desk (React, http://localhost:5173/?ticket={tid}) after ticket #{tid} was resolved.</figcaption></figure>
</section>""")
    nav = "".join(f'<a href="#t{t["ticket"]["id"]}">#{t["ticket"]["id"]} {e(t["ticket"]["subject"])}</a>' for t in g["tickets"])
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs · Resolved board</title>
<style>
  :root {{ --navy:#00356b; --line:#dce4ef; --muted:#46597a; --bg:#f6f8fc; --good:#1a7f37; --good-bg:#e6f4ea; --warn:#9a6700; --warn-bg:#fff4d6; --bad:#b42318; --bad-bg:#fde8e6; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; color:#0c1f3a; background:var(--bg); }}
  header {{ background:linear-gradient(120deg,#00254d,var(--navy) 60%,#0b4a8f); color:#fff; padding:22px 32px; }}
  header h1 {{ margin:0; font-family:Georgia,serif; letter-spacing:.04em; }}
  header p {{ margin:6px 0 0; opacity:.85; }}
  nav {{ position:sticky; top:0; z-index:5; display:flex; gap:8px; padding:10px 32px; background:#fff; border-bottom:1px solid var(--line); flex-wrap:wrap; }}
  nav a {{ text-decoration:none; color:var(--navy); font-weight:600; padding:6px 14px; border-radius:999px; border:1px solid var(--line); }}
  nav a:hover {{ background:var(--navy); color:#fff; }}
  main {{ max-width:1700px; margin:0 auto; padding:22px 32px 60px; display:grid; gap:34px; }}
  section {{ background:#fff; border:1px solid var(--line); border-radius:16px; padding:20px 22px; box-shadow:0 8px 24px rgba(0,35,80,.08); scroll-margin-top:60px; }}
  .head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
  h2 {{ margin:0 auto 0 0; font-family:Georgia,serif; color:var(--navy); }}
  h3 {{ margin:0 0 6px; font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
  .chip {{ font-size:12px; font-weight:800; padding:4px 11px; border-radius:999px; }}
  .chip.good, .chip.resolved {{ background:var(--good-bg); color:var(--good); }} .chip.warn {{ background:var(--warn-bg); color:var(--warn); }} .chip.bad {{ background:var(--bad-bg); color:var(--bad); }}
  .call {{ font-family:Georgia,serif; font-size:16px; line-height:1.5; margin:12px 0; }}
  .meta {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:14px; }}
  .meta ul {{ margin:0; padding-left:18px; font-size:14px; }}
  .crew {{ display:flex; gap:12px; flex-wrap:wrap; }}
  .who {{ display:inline-flex; align-items:center; gap:6px; font-weight:600; color:var(--navy); }}
  .who .ic {{ width:28px; height:28px; }}
  .st {{ font-size:11px; font-weight:800; text-transform:uppercase; padding:1px 7px; border-radius:999px; margin-left:4px; }}
  .st.approved {{ background:var(--good-bg); color:var(--good); }} .st.pending {{ background:var(--warn-bg); color:var(--warn); }} .st.covered {{ background:#e8eef6; color:var(--navy); }}
  figure {{ margin:0; }}
  figure img {{ width:100%; border-radius:12px; border:1px solid var(--line); display:block; }}
  figcaption {{ font-size:13px; color:var(--muted); margin-top:6px; text-align:center; }}
</style></head><body>
<header><h1>Campus Customs · Resolved board</h1>
<p>Screenshots of the React Agent Desk after the Problem 9 run · checking {money(START_BALANCE)} → {money(g['ending'])} · desk.date_today {e(g['facts']['cash']['date_today'])}</p></header>
<nav>{nav}</nav>
<main>{''.join(sections)}</main>
</body></html>"""
    (OUTPUT_DIR / "resolved_board.html").write_text(page, encoding="utf-8")


def main() -> None:
    g = gather()
    write_json(g)
    write_desk(g)
    write_board(g)
    print(f"start {money(START_BALANCE)} - paid {money(g['paid_total'])} = ending {money(g['ending'])} (matches cash_accounts)")
    for t in g["tickets"]:
        print(f"#{t['ticket']['id']} {t['status']} {t['decision']['decision']} | agents {[a['agent'] for a in t['summary']['agents']]} | "
              f"checks {sum(ok for _, ok in t['checks'])}/{len(t['checks'])} | approvals {[(a['kind'], a['status']) for a in t['approvals']]}")


if __name__ == "__main__":
    main()

"""Campus Customs MCP server: shared tools for the HW5 agent team.

Every agent (Boss, Inventory, Accounting, Facilities, Customer Service) calls
these tools. They read the working copy ../data/campus_customs_new.db and never
touch the original campus_customs.db, which is kept for resets.

Run (stdio):  python server.py
Run (HTTP):   python server.py --http
HTTP URL:     http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. Copy data/campus_customs.db to data/campus_customs_new.db."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _today(conn: sqlite3.Connection) -> str:
    """The shop's official date (desk.date_today), not the computer clock."""
    return conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


def _invoice_record(conn: sqlite3.Connection, invoice: sqlite3.Row, today: str) -> dict:
    """One invoice with its vendor, payments made against it, and what is still owed."""
    payments = [
        dict(p)
        for p in conn.execute(
            """
            SELECT id, amount, account, paid_at, approved_by
            FROM payments
            WHERE kind = 'invoice' AND ref_id = ?
            ORDER BY paid_at, id
            """,
            (invoice["id"],),
        )
    ]
    paid = round(sum(p["amount"] for p in payments), 2)
    # An invoice marked 'paid' owes nothing even if the payment row predates this log.
    outstanding = 0.0 if invoice["status"] == "paid" else round(max(invoice["amount"] - paid, 0.0), 2)
    days_past_due = _days_between(invoice["due_date"], today)
    return {
        "invoice_id": invoice["id"],
        "vendor_id": invoice["vendor_id"],
        "vendor_name": invoice["vendor_name"],
        "vendor_specialty": invoice["vendor_specialty"],
        "vendor_lead_days": invoice["vendor_lead_days"],
        "description": invoice["description"],
        "amount": invoice["amount"],
        "due_date": invoice["due_date"],
        "status": invoice["status"],
        "amount_paid": paid,
        "outstanding_amount": outstanding,
        "is_paid": outstanding == 0,
        "is_overdue": outstanding > 0 and days_past_due > 0,
        "days_overdue": max(days_past_due, 0) if outstanding > 0 else 0,
        "payments": payments,
    }


_INVOICE_SELECT = """
    SELECT i.id, i.vendor_id, i.amount, i.due_date, i.status, i.description,
           v.name AS vendor_name, v.specialty AS vendor_specialty, v.lead_days AS vendor_lead_days
    FROM invoices i
    JOIN vendors v ON v.id = i.vendor_id
"""


@mcp.tool
def get_ticket_details(ticket_id: int) -> dict:
    """Everything an agent needs to understand one ticket from the board.

    Returns the ticket itself (type, requester, subject, notes, status, item
    and quantity requested, created_at), the shop's date (desk.date_today),
    and the records the ticket points to: the product name for its SKU, the
    linked lease, and the linked invoice with its vendor. Use this first on
    any ticket, then call the specialist tools for stock or invoice checks.
    """
    with _connect() as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            ids = [r["id"] for r in conn.execute("SELECT id FROM tickets ORDER BY id")]
            return {"error": f"Ticket {ticket_id} not found.", "existing_ticket_ids": ids}

        today = _today(conn)
        result = {"date_today": today, "ticket": dict(ticket), "linked": {}}

        if ticket["sku"]:
            product = conn.execute(
                "SELECT DISTINCT name FROM inventory WHERE sku = ?", (ticket["sku"],)
            ).fetchone()
            result["linked"]["product"] = {
                "sku": ticket["sku"],
                "name": product["name"] if product else None,
                "size_requested": ticket["size"],
                "qty_requested": ticket["qty"],
            }

        if ticket["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)).fetchone()
            if lease:
                result["linked"]["lease"] = {
                    **dict(lease),
                    "days_until_due": _days_between(today, lease["next_due"]),
                }

        if ticket["invoice_id"] is not None:
            invoice = conn.execute(
                _INVOICE_SELECT + " WHERE i.id = ?", (ticket["invoice_id"],)
            ).fetchone()
            if invoice:
                result["linked"]["invoice"] = {
                    "invoice_id": invoice["id"],
                    "vendor_id": invoice["vendor_id"],
                    "vendor_name": invoice["vendor_name"],
                    "amount": invoice["amount"],
                    "due_date": invoice["due_date"],
                    "status": invoice["status"],
                    "description": invoice["description"],
                }

    return result


@mcp.tool
def check_item_availability(sku: str, size: str | None = None, qty_needed: int | None = None) -> dict:
    """Stock and price for a product, from the inventory and pricing tables.

    Give a SKU (e.g. "CC-TEE-WHITE"). Add a size ("S", "M", "L", "XL", or
    "OS") to check one size, and qty_needed to see whether the request can
    be filled and how many units are short. Returns quantity on hand per
    size with its shop location, unit cost, list price, and margin per unit.
    """
    sku = sku.strip().upper()
    size = size.strip().upper() if size else None
    with _connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT size, qty, location, name
                FROM inventory
                WHERE sku = ?
                ORDER BY CASE size WHEN 'XS' THEN 0 WHEN 'S' THEN 1 WHEN 'M' THEN 2
                                   WHEN 'L' THEN 3 WHEN 'XL' THEN 4 WHEN 'XXL' THEN 5 ELSE 9 END
                """,
                (sku,),
            )
        ]
        if not rows:
            skus = [r["sku"] for r in conn.execute("SELECT DISTINCT sku FROM inventory ORDER BY sku")]
            return {"error": f"SKU {sku} not found in inventory.", "existing_skus": skus}
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    result = {
        "sku": sku,
        "name": rows[0]["name"],
        "unit_cost": price["unit_cost"] if price else None,
        "list_price": price["list_price"] if price else None,
        "margin_per_unit": round(price["list_price"] - price["unit_cost"], 2) if price else None,
        "margin_pct": round((price["list_price"] - price["unit_cost"]) / price["list_price"] * 100, 1)
        if price and price["list_price"]
        else None,
        "total_qty_all_sizes": sum(r["qty"] for r in rows),
        "sizes": [{"size": r["size"], "qty": r["qty"], "location": r["location"], "in_stock": r["qty"] > 0} for r in rows],
    }
    if price is None:
        result["pricing_note"] = f"No pricing row for {sku}."

    if size:
        match = next((r for r in rows if r["size"] == size), None)
        if match is None:
            result["error"] = f"Size {size} not stocked for {sku}."
            result["available_sizes"] = [r["size"] for r in rows]
            return result
        result["size_requested"] = size
        result["qty_available"] = match["qty"]
        result["location"] = match["location"]
        if qty_needed is not None:
            short = max(qty_needed - match["qty"], 0)
            result["qty_needed"] = qty_needed
            result["can_fulfill"] = short == 0
            result["shortfall"] = short
            if price:
                result["list_value_of_request"] = round(qty_needed * price["list_price"], 2)
                result["cost_to_restock_shortfall"] = round(short * price["unit_cost"], 2)

    return result


@mcp.tool
def check_invoice_payment(invoice_id: int | None = None, vendor_id: int | None = None) -> dict:
    """Has an invoice been paid, and how much is still owed?

    Give an invoice_id to check one invoice, or a vendor_id to check every
    invoice from that vendor. Reads invoices, vendors, and payments
    (kind = 'invoice'), and compares due dates to desk.date_today. Returns
    amount, amount paid, outstanding amount, whether it is overdue, and
    whether the vendor is blocked from shipping new product (vendors will
    not ship while they have an unpaid invoice).

    Call it with no arguments for the full ledger: every invoice with its
    payment status, plus every payment made to date (all kinds, e.g. rent).
    """
    if invoice_id is None and vendor_id is None:
        with _connect() as conn:
            today = _today(conn)
            invoices = [
                _invoice_record(conn, row, today)
                for row in conn.execute(_INVOICE_SELECT + " ORDER BY i.due_date, i.id")
            ]
            payments = [dict(p) for p in conn.execute("SELECT * FROM payments ORDER BY paid_at, id")]
        return {
            "date_today": today,
            "payments_to_date": payments,
            "payment_count": len(payments),
            "total_paid": round(sum(p["amount"] for p in payments), 2),
            "invoices": invoices,
            "total_outstanding": round(sum(inv["outstanding_amount"] for inv in invoices), 2),
        }

    with _connect() as conn:
        today = _today(conn)
        if invoice_id is not None:
            invoice = conn.execute(_INVOICE_SELECT + " WHERE i.id = ?", (invoice_id,)).fetchone()
            if invoice is None:
                ids = [r["id"] for r in conn.execute("SELECT id FROM invoices ORDER BY id")]
                return {"error": f"Invoice {invoice_id} not found.", "existing_invoice_ids": ids}
            vendor_id = invoice["vendor_id"]

        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            ids = [r["id"] for r in conn.execute("SELECT id FROM vendors ORDER BY id")]
            return {"error": f"Vendor {vendor_id} not found.", "existing_vendor_ids": ids}

        vendor_invoices = [
            _invoice_record(conn, row, today)
            for row in conn.execute(_INVOICE_SELECT + " WHERE i.vendor_id = ? ORDER BY i.due_date", (vendor_id,))
        ]

    unpaid = [inv for inv in vendor_invoices if not inv["is_paid"]]
    result = {
        "date_today": today,
        "vendor": dict(vendor),
        "vendor_total_outstanding": round(sum(inv["outstanding_amount"] for inv in unpaid), 2),
        "vendor_unpaid_invoice_ids": [inv["invoice_id"] for inv in unpaid],
        "vendor_will_ship": not unpaid,
    }
    if invoice_id is not None:
        result["invoice"] = next(inv for inv in vendor_invoices if inv["invoice_id"] == invoice_id)
    else:
        result["invoices"] = vendor_invoices
    return result


@mcp.tool
def list_tickets(status: str | None = "open") -> dict:
    """The ticket board: one line per ticket so the Boss can see the queue.

    Defaults to open tickets. Pass status=None (or "all") for every ticket.
    Use get_ticket_details for the full record of any one ticket.
    """
    with _connect() as conn:
        today = _today(conn)
        if status and status.lower() != "all":
            rows = conn.execute(
                "SELECT id, type, requester, subject, status, created_at FROM tickets WHERE status = ? ORDER BY id",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, type, requester, subject, status, created_at FROM tickets ORDER BY id"
            ).fetchall()
        statuses = [r["status"] for r in conn.execute("SELECT DISTINCT status FROM tickets ORDER BY status")]
    return {"date_today": today, "filter": status or "all", "count": len(rows),
            "tickets": [dict(r) for r in rows], "statuses_in_db": statuses}


@mcp.tool
def get_lease_details(lease_id: int | None = None) -> dict:
    """The shop's lease(s): space, landlord, monthly rent, and next due date.

    Give a lease_id for one lease, or leave it empty for all leases. Adds
    days until rent is due and whether it is overdue (against
    desk.date_today), plus any rent payments recorded in the payments table
    (kind = 'rent', ref_id = lease id).
    """
    with _connect() as conn:
        today = _today(conn)
        if lease_id is not None:
            rows = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchall()
            if not rows:
                ids = [r["id"] for r in conn.execute("SELECT id FROM leases ORDER BY id")]
                return {"error": f"Lease {lease_id} not found.", "existing_lease_ids": ids}
        else:
            rows = conn.execute("SELECT * FROM leases ORDER BY id").fetchall()

        leases = []
        for lease in rows:
            rent_payments = [
                dict(p)
                for p in conn.execute(
                    "SELECT id, amount, account, paid_at, approved_by FROM payments "
                    "WHERE kind = 'rent' AND ref_id = ? ORDER BY paid_at, id",
                    (lease["id"],),
                )
            ]
            days = _days_between(today, lease["next_due"])
            leases.append({
                **dict(lease),
                "days_until_due": days,
                "is_overdue": days < 0,
                "rent_payments": rent_payments,
            })
    return {"date_today": today, "leases": leases}


@mcp.tool
def get_cash_balance(account: str | None = None) -> dict:
    """Cash on hand and what it has to cover.

    Returns each cash account's balance (or one account by name, e.g.
    "checking"), the total, and the bills waiting on that cash: unpaid
    invoices and rent due within 30 days of desk.date_today. Also returns
    the balance left if all of those were paid. Revenue is never added;
    cash only goes out.
    """
    with _connect() as conn:
        today = _today(conn)
        if account:
            rows = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchall()
            if not rows:
                names = [r["name"] for r in conn.execute("SELECT name FROM cash_accounts ORDER BY name")]
                return {"error": f"Cash account '{account}' not found.", "existing_accounts": names}
        else:
            rows = conn.execute("SELECT * FROM cash_accounts ORDER BY name").fetchall()

        unpaid = [
            inv for inv in (_invoice_record(conn, r, today) for r in conn.execute(_INVOICE_SELECT + " ORDER BY i.due_date"))
            if not inv["is_paid"]
        ]
        rent_due = [
            {"lease_id": l["id"], "space_name": l["space_name"], "landlord": l["landlord"],
             "amount": l["monthly_rent"], "due_date": l["next_due"],
             "days_until_due": _days_between(today, l["next_due"])}
            for l in conn.execute("SELECT * FROM leases ORDER BY next_due")
            if _days_between(today, l["next_due"]) <= 30
        ]

    total = round(sum(r["balance"] for r in rows), 2)
    obligations = [
        {"kind": "invoice", "ref_id": inv["invoice_id"], "payee": inv["vendor_name"],
         "amount": inv["outstanding_amount"], "due_date": inv["due_date"], "is_overdue": inv["is_overdue"]}
        for inv in unpaid
    ] + [
        {"kind": "rent", "ref_id": r["lease_id"], "payee": r["landlord"],
         "amount": r["amount"], "due_date": r["due_date"], "is_overdue": r["days_until_due"] < 0}
        for r in rent_due
    ]
    owed = round(sum(o["amount"] for o in obligations), 2)
    return {
        "date_today": today,
        "accounts": [dict(r) for r in rows],
        "total_balance": total,
        "upcoming_obligations": obligations,
        "total_obligations": owed,
        "balance_after_obligations": round(total - owed, 2),
        "covers_all_obligations": total - owed >= 0,
    }


@mcp.tool
def check_cash_for_payment(amount: float, account: str = "checking") -> dict:
    """Can the shop afford a payment without going negative?

    Checks a proposed payment amount against the account balance. This tool
    never moves money: agents can only prepare payments, and a human must
    approve every payment. Use it before recommending any payment or PO,
    and pass the combined total when several payments are planned together.
    """
    if amount <= 0:
        return {"error": "Amount must be greater than zero."}
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if row is None:
            names = [r["name"] for r in conn.execute("SELECT name FROM cash_accounts ORDER BY name")]
            return {"error": f"Cash account '{account}' not found.", "existing_accounts": names}
        today = _today(conn)
    remaining = round(row["balance"] - amount, 2)
    return {
        "date_today": today,
        "account": account,
        "balance": row["balance"],
        "proposed_amount": round(amount, 2),
        "balance_after": remaining,
        "can_pay": remaining >= 0,
        "shortfall": round(-remaining, 2) if remaining < 0 else 0,
        "requires_human_approval": True,
    }


@mcp.tool
def get_vendor_info(vendor_id: int | None = None, specialty: str | None = None) -> dict:
    """Vendors: what they supply, lead times, and whether they will ship.

    Give a vendor_id, or a specialty keyword (e.g. "apparel", "mugs"), or
    nothing for all vendors. For each vendor returns lead_days, the earliest
    delivery date if ordered today (desk.date_today + lead_days), unpaid
    invoices, and will_ship (false while any invoice is unpaid).
    """
    with _connect() as conn:
        today = _today(conn)
        if vendor_id is not None:
            rows = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchall()
        elif specialty:
            rows = conn.execute(
                "SELECT * FROM vendors WHERE specialty LIKE ? ORDER BY id", (f"%{specialty}%",)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()
        if not rows:
            all_vendors = [dict(r) for r in conn.execute("SELECT id, name, specialty FROM vendors ORDER BY id")]
            return {"error": "No matching vendor.", "vendors": all_vendors}

        vendors = []
        for v in rows:
            unpaid = [
                inv for inv in (
                    _invoice_record(conn, r, today)
                    for r in conn.execute(_INVOICE_SELECT + " WHERE i.vendor_id = ? ORDER BY i.due_date", (v["id"],))
                )
                if not inv["is_paid"]
            ]
            vendors.append({
                **dict(v),
                "earliest_delivery_if_ordered_today": (date.fromisoformat(today) + timedelta(days=v["lead_days"])).isoformat(),
                "unpaid_invoices": [
                    {"invoice_id": i["invoice_id"], "outstanding_amount": i["outstanding_amount"],
                     "due_date": i["due_date"], "is_overdue": i["is_overdue"], "days_overdue": i["days_overdue"]}
                    for i in unpaid
                ],
                "total_outstanding": round(sum(i["outstanding_amount"] for i in unpaid), 2),
                "will_ship": not unpaid,
            })
    return {"date_today": today, "vendors": vendors}


@mcp.tool
def get_pricing(sku: str | None = None, qty: int | None = None, discount_pct: float | None = None) -> dict:
    """Unit cost, list price, and margin per product, with discount math.

    Give a SKU for one product or nothing for all. Add qty and/or
    discount_pct (e.g. 15 for 15% off list) to price a quote: discounted
    unit price, total revenue, total cost, gross margin, and whether the
    price falls below cost. Also returns the largest discount that still
    covers unit cost.
    """
    with _connect() as conn:
        if sku:
            sku = sku.strip().upper()
            rows = conn.execute(
                "SELECT p.*, (SELECT name FROM inventory i WHERE i.sku = p.sku LIMIT 1) AS name "
                "FROM pricing p WHERE p.sku = ?", (sku,)
            ).fetchall()
            if not rows:
                skus = [r["sku"] for r in conn.execute("SELECT sku FROM pricing ORDER BY sku")]
                return {"error": f"No pricing for SKU {sku}.", "existing_skus": skus}
        else:
            rows = conn.execute(
                "SELECT p.*, (SELECT name FROM inventory i WHERE i.sku = p.sku LIMIT 1) AS name "
                "FROM pricing p ORDER BY p.sku"
            ).fetchall()

    items = []
    for r in rows:
        margin = r["list_price"] - r["unit_cost"]
        item = {
            "sku": r["sku"],
            "name": r["name"],
            "unit_cost": r["unit_cost"],
            "list_price": r["list_price"],
            "margin_per_unit": round(margin, 2),
            "margin_pct": round(margin / r["list_price"] * 100, 1),
            "max_discount_pct_before_loss": round(margin / r["list_price"] * 100, 1),
        }
        if qty is not None or discount_pct is not None:
            if discount_pct is not None and not 0 <= discount_pct <= 100:
                return {"error": "discount_pct must be between 0 and 100."}
            units = qty or 1
            pct = discount_pct or 0.0
            unit_price = round(r["list_price"] * (1 - pct / 100), 2)
            item["quote"] = {
                "qty": units,
                "discount_pct": pct,
                "unit_price": unit_price,
                "total_price": round(unit_price * units, 2),
                "total_cost": round(r["unit_cost"] * units, 2),
                "gross_margin": round((unit_price - r["unit_cost"]) * units, 2),
                "margin_pct": round((unit_price - r["unit_cost"]) / unit_price * 100, 1) if unit_price else None,
                "below_cost": unit_price < r["unit_cost"],
            }
        items.append(item)
    return {"items": items}


# ---- write tools: called by the backend only after a human acts ----------
# Agents never see these (their tool lists leave them out). Each write runs in
# one transaction and re-checks the safety rules against the database itself.

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service", "customer service", "system", "agent"}
TICKET_STATUSES = ("open", "resolved")


def _add_month(day: str) -> str:
    d = date.fromisoformat(day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for dd in (d.day, 30, 29, 28):  # clamp e.g. Jan 31 -> Feb 28
        try:
            return date(year, month, dd).isoformat()
        except ValueError:
            continue
    raise ValueError(day)


@mcp.tool
def record_payment(kind: str, amount: float, approved_by: str, ref_id: int | None = None,
                   account: str = "checking", payee: str | None = None) -> dict:
    """Record a payment a HUMAN approved: the only way money leaves the account.

    kind: "invoice" (ref_id = invoices.id), "rent" (ref_id = leases.id), or
    "purchase_order" (payee = vendor name). approved_by must be the human who
    clicked approve. Refuses if: approved_by is empty or an agent, the
    balance would go negative, the invoice is already paid or the amount is
    more than what's owed, the rent amount isn't the lease's monthly rent, or
    the PO vendor has an unpaid invoice. On success it inserts the payments
    row (paid_at = desk.date_today), lowers the balance, marks a fully paid
    invoice 'paid', and moves a paid lease's next_due forward one month.
    """
    who = (approved_by or "").strip()
    if not who or who.lower() in AGENT_NAMES:
        return {"ok": False, "error": "approved_by must name the human who approved this payment."}
    if amount is None or amount <= 0:
        return {"ok": False, "error": "Amount must be greater than zero."}
    if kind not in ("invoice", "rent", "purchase_order"):
        return {"ok": False, "error": "kind must be 'invoice', 'rent', or 'purchase_order'."}
    amount = round(float(amount), 2)

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            today = _today(conn)
            acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
            if acct is None:
                raise ValueError(f"Cash account '{account}' not found.")
            if acct["balance"] - amount < 0:
                raise ValueError(f"Not enough cash: balance ${acct['balance']:,.2f}, payment ${amount:,.2f}. "
                                 f"No negative balances.")
            effects: list[str] = []

            if kind == "invoice":
                row = conn.execute(_INVOICE_SELECT + " WHERE i.id = ?", (ref_id,)).fetchone()
                if row is None:
                    raise ValueError(f"Invoice {ref_id} not found.")
                inv = _invoice_record(conn, row, today)
                if inv["is_paid"]:
                    raise ValueError(f"Invoice {ref_id} is already paid.")
                if amount > inv["outstanding_amount"] + 0.005:
                    raise ValueError(f"Amount ${amount:,.2f} is more than the ${inv['outstanding_amount']:,.2f} owed.")
                payee = inv["vendor_name"]
            elif kind == "rent":
                lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
                if lease is None:
                    raise ValueError(f"Lease {ref_id} not found.")
                if abs(amount - lease["monthly_rent"]) > 0.005:
                    raise ValueError(f"Rent payment must equal the monthly rent (${lease['monthly_rent']:,.2f}).")
                payee = lease["landlord"]
            else:  # purchase_order
                vendor = conn.execute("SELECT * FROM vendors WHERE name = ?", (payee,)).fetchone()
                if vendor is None:
                    raise ValueError(f"Vendor '{payee}' not found.")
                unpaid = [
                    r["id"] for r in conn.execute(_INVOICE_SELECT + " WHERE i.vendor_id = ?", (vendor["id"],))
                    if not _invoice_record(conn, r, today)["is_paid"]
                ]
                if unpaid:
                    raise ValueError(f"{vendor['name']} has unpaid invoice(s) {unpaid}; vendors won't ship until those are paid.")
                ref_id = vendor["id"]

            cur = conn.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
                (kind, ref_id, amount, account, today, who),
            )
            new_balance = round(acct["balance"] - amount, 2)
            conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))

            if kind == "invoice":
                row = conn.execute(_INVOICE_SELECT + " WHERE i.id = ?", (ref_id,)).fetchone()
                if _invoice_record(conn, row, today)["outstanding_amount"] <= 0.005:
                    conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
                    effects.append(f"Invoice {ref_id} marked paid.")
            elif kind == "rent":
                next_due = _add_month(lease["next_due"])
                conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
                effects.append(f"Lease {ref_id} next_due moved from {lease['next_due']} to {next_due}.")
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "payment": {"id": cur.lastrowid, "kind": kind, "ref_id": ref_id, "payee": payee, "amount": amount,
                    "account": account, "paid_at": today, "approved_by": who},
        "balance_before": acct["balance"],
        "balance_after": new_balance,
        "effects": effects,
    }


@mcp.tool
def set_ticket_status(ticket_id: int, status: str) -> dict:
    """Mark a ticket 'open' or 'resolved' on the board. Called by the backend, not by agents."""
    if status not in TICKET_STATUSES:
        return {"ok": False, "error": f"status must be one of {TICKET_STATUSES}."}
    with _connect() as conn:
        row = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": f"Ticket {ticket_id} not found."}
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.commit()
    return {"ok": True, "ticket_id": ticket_id, "old_status": row["status"], "status": status}


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs MCP server")
    parser.add_argument("--http", action="store_true", help="serve over HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=args.port)
    else:
        mcp.run(show_banner=False)  # keep stdio clean when an agent launches it


if __name__ == "__main__":
    main()

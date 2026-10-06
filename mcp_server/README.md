# Campus Customs MCP Server

The shared toolbox for the Campus Customs agent team. Every agent (Boss, Inventory, Accounting, Facilities, Customer Service) gets its facts about the shop from these tools; no agent queries the database itself. That keeps every answer tied to real data and keeps the business rules in one place.

Built with [FastMCP](https://gofastmcp.com) 4.x. Server name: `campus-customs`.

## Database

- **Uses:** `../data/campus_customs_new.db`, the working copy.
- **Never touches:** `../data/campus_customs.db`, the original. Before a full run, reset the working copy from it:

```powershell
..\.venv\Scripts\python.exe ..\backend\reset_db.py
```

(`backend/run_team.py --all` does this automatically.)

- **Today's date:** every date check uses `desk.date_today` (`2026-08-31`), not the computer's clock. Every tool that deals with dates returns it as `date_today`.

## Tools

There are 11 tools: **9 read-only tools** that the agents use, and **2 write tools** that only the backend calls after a human acts (see *Write tools* below). If an ID, SKU, size, or account doesn't exist, the tool returns an `error` plus the valid options instead of guessing. Every value comes straight from the database or is simple math on it (margins, shortfalls, days overdue, balance after payments).

| Tool | Inputs | Reads | Returns | Main users |
|---|---|---|---|---|
| `list_tickets` | `status` (default `"open"`, or `"all"`) | `tickets`, `desk` | One line per ticket: id, type, requester, subject, status, created_at. | Boss |
| `get_ticket_details` | `ticket_id` | `tickets`, `desk`, `inventory`, `leases`, `invoices`, `vendors` | The full ticket plus what it links to: product name, the lease (with days until rent is due), and the invoice with its vendor. | All agents |
| `check_item_availability` | `sku`, optional `size`, `qty_needed` | `inventory`, `pricing` | Quantity and aisle per size, unit cost, list price, margin. With a size: quantity available. With `qty_needed`: whether it can be filled, shortfall, request value at list price, cost to restock the shortfall. | Inventory |
| `get_pricing` | optional `sku`, `qty`, `discount_pct` | `pricing`, `inventory` | Unit cost, list price, margin, and the largest discount before a loss. With `qty`/`discount_pct`: a quote with unit price, total, total cost, gross margin, margin %, and `below_cost`. | Accounting, Inventory |
| `get_vendor_info` | optional `vendor_id` or `specialty` | `vendors`, `invoices`, `payments`, `desk` | Specialty, `lead_days`, earliest delivery if ordered today, unpaid invoices, and `will_ship` (false while any invoice is unpaid). | Inventory, Accounting |
| `check_invoice_payment` | `invoice_id`, or `vendor_id`, or **nothing** | `invoices`, `vendors`, `payments`, `desk` | Amount, paid, outstanding, overdue and days overdue, payment rows, the vendor's unpaid total, and `vendor_will_ship`. With no arguments: the full ledger (every payment to date and every invoice). | Accounting |
| `get_cash_balance` | optional `account` | `cash_accounts`, `invoices`, `vendors`, `payments`, `leases`, `desk` | Balance per account and in total, every upcoming obligation (unpaid invoices and rent due within 30 days), and the balance left after them. Revenue is never added. | Accounting |
| `check_cash_for_payment` | `amount`, `account` (default `"checking"`) | `cash_accounts`, `desk` | Balance, balance after the payment, `can_pay`, shortfall, and `requires_human_approval: true`. A check only; it never pays. | Accounting, backend safety check |
| `get_lease_details` | optional `lease_id` | `leases`, `payments`, `desk` | Space, landlord, monthly rent, next due date, days until due, overdue flag, and rent payments on record. | Facilities |

### Write tools (backend only)

The agents never see these tools; each agent's allowlist in `backend/agents/*.py` leaves them out. Only `backend/main.py` calls them.

| Tool | Inputs | Writes | What it does |
|---|---|---|---|
| `record_payment` | `kind` (`invoice` / `rent` / `purchase_order`), `amount`, `approved_by`, `ref_id`, `account`, `payee` | `payments`, `cash_accounts`, `invoices`, `leases` | Called when a human clicks Approve. In one transaction it refuses: an empty or agent `approved_by`, a balance that would go negative, an invoice that's already paid or an amount above what's owed, a rent amount that isn't the monthly rent, or a PO to a vendor with an unpaid invoice. Otherwise it inserts the payment (`paid_at = desk.date_today`), lowers the balance, marks a fully paid invoice `paid`, and moves a paid lease's `next_due` forward one month. |
| `set_ticket_status` | `ticket_id`, `status` (`open` / `resolved`) | `tickets` | Moves a ticket between open and resolved on the board. |

### Payment conventions

The `payments` table is empty at the start. When payments are recorded (only after a human approves), the tools read them as:

- invoice payments: `kind = 'invoice'`, `ref_id = invoices.id`
- rent payments: `kind = 'rent'`, `ref_id = leases.id`
- `approved_by` is the human who approved it

## Who connects to it

- **The FastAPI backend** (`backend/main.py`, `uvicorn main:app --reload --port 8000`). It reads tickets and cash, and calls the write tools after human approval, a team run, or a reset.
- **The agent team** (`backend/`). `backend/config.py` starts this server over stdio and shares one connection across all five PydanticAI agents. Each agent only sees the tools its role needs (see `output/harness.md`). Set `CAMPUS_MCP_URL=http://127.0.0.1:8001/mcp` to use an already-running HTTP server instead.
- **Claude Code (the vibe coder)**, through the `campus-customs` entry in the project-root `.mcp.json`. Smoke-test evidence is in `output/mcp_smoke.json`.

## Run it yourself

From this folder, using the HW5 virtual environment:

```powershell
..\.venv\Scripts\python.exe server.py          # stdio (for an MCP client that launches it)
..\.venv\Scripts\python.exe server.py --http   # HTTP at http://127.0.0.1:8001/mcp
```

Requires `fastmcp` (listed in `../requirements.txt`).

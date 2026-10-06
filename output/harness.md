# Campus Customs Agent Harness

Everything the Campus Customs agent team runs on, in one place. **Contents:**

1. Tables
2. How the tables connect
3. MCP tools
4. The five agents (delegation, routing, audit)
5. Backend routes
6. The dashboard
7. Problem 9 run
8. Safety rules

The tables section covers what the agent team needs to know about the shop's database.

- **Working database:** `data/campus_customs_new.db`. The MCP server and backend read and write this copy.
- **Reset source:** `data/campus_customs.db`. Never modified. Copy it over the working database before every full run.
- **Shop "today":** `desk.date_today` (currently `2026-08-31`). Use it for every overdue or due-soon check, not the computer's clock.

## Tables

### `tickets` (3 rows): the work board

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Ticket number (101–103) |
| `type` | TEXT | `customer_order`, `rent_notice`, `price_override` |
| `requester` | TEXT | Who asked (customer, landlord, student org) |
| `subject` | TEXT | Short title |
| `sku` | TEXT, nullable | Product involved; links to `inventory.sku` and `pricing.sku` |
| `size` | TEXT, nullable | Size involved; with `sku` it identifies the `inventory` row |
| `qty` | INTEGER, nullable | Units requested |
| `lease_id` | INTEGER FK, nullable | → `leases.id` |
| `invoice_id` | INTEGER FK, nullable | → `invoices.id` |
| `status` | TEXT | `open` now; agents move tickets to resolved states |
| `notes` | TEXT | The requester's message in plain words |
| `created_at` | TEXT | ISO timestamp with timezone |

**Why it matters for agents:** This is the Boss's inbox. Each ticket is one unit of work. Its `type` decides who gets it, its foreign keys point to the facts needed to solve it, and its `status` is how the team marks it done.

### `inventory` (10 rows): stock on the shelf

| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT, PK part | Product code, e.g. `CC-TEE-WHITE` |
| `name` | TEXT | Display name |
| `size` | TEXT, PK part | `S`/`M`/`L`/`XL`, or `OS` (one size) |
| `qty` | INTEGER | Units on hand; `0` means sold out |
| `location` | TEXT | Aisle in the shop |

**Why it matters for agents:** Inventory checks stock here by `(sku, size)` before anyone promises a customer anything, and finds shortfalls that turn into reprint orders. Stock is tracked per size, so "we have hoodies" isn't enough.

### `pricing` (4 rows): cost and price per product

| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT PK | One row per product (all sizes share a price) |
| `unit_cost` | REAL | What the shop pays per unit |
| `list_price` | REAL | Normal selling price |

**Why it matters for agents:** Accounting uses it to cost purchase orders (`qty × unit_cost`) and to check margins on discount requests. A discount must stay above `unit_cost`.

### `vendors` (3 rows): suppliers

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Referenced by `invoices.vendor_id` |
| `name` | TEXT | Bulldog Print Co, Elm City Gifts, QuickShip CT |
| `specialty` | TEXT | What they supply (apparel reprint, mugs and small goods, local courier) |
| `lead_days` | INTEGER | Days from order to delivery (5, 3, 1) |

**Why it matters for agents:** All lead times come from here, so this is how agents give customers honest restock dates. There is no SKU→vendor column, so agents pick a vendor by `specialty` (apparel → Bulldog Print Co, mugs → Elm City Gifts).

### `invoices` (1 row): bills the shop owes

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Referenced by `tickets.invoice_id` |
| `vendor_id` | INTEGER FK | → `vendors.id` |
| `amount` | REAL | Amount owed |
| `due_date` | TEXT | Overdue if before `desk.date_today` |
| `status` | TEXT | `open` = unpaid |
| `description` | TEXT | What the bill was for |

**Why it matters for agents:** Accounting tracks what's owed and what's overdue here. It also controls the supply chain: **a vendor with an open invoice will not ship new product**, so a reprint can't happen until that vendor's bill is paid.

### `leases` (1 row): the shop space

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Referenced by `tickets.lease_id` |
| `space_name` | TEXT | Chapel Street shop |
| `landlord` | TEXT | Elm City Properties |
| `monthly_rent` | REAL | 2,400.00 |
| `next_due` | TEXT | Next rent date; roll forward a month once paid |
| `notes` | TEXT | Free text |

**Why it matters for agents:** Facilities owns the shop space and checks rent amounts and due dates here. Accounting then pays the rent through a human-approved payment.

### `cash_accounts` (1 row): money available

| Field | Type | Notes |
|---|---|---|
| `name` | TEXT PK | `checking` |
| `balance` | REAL | 3,400.00 |
| `date` | TEXT | Date the balance was recorded |

**Why it matters for agents:** This is the hard limit on every decision that spends money. No payment can go out if it would push the balance below zero. Cash only goes out; customer sales are not added.

### `payments` (0 rows): money that left the account

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-assigned |
| `kind` | TEXT | What was paid, e.g. `invoice`, `rent`, `po` |
| `ref_id` | INTEGER | ID of the thing paid (`invoices.id`, `leases.id`, …); no enforced FK |
| `amount` | REAL | Amount paid |
| `account` | TEXT | Account it came from; matches `cash_accounts.name` |
| `paid_at` | TEXT | Date paid |
| `approved_by` | TEXT, required | The human who approved it |

**Why it matters for agents:** This is the audit trail. Agents can *prepare* a payment, but a row is only written after a human approves it, and `approved_by` can't be empty. Each payment must also lower `cash_accounts.balance` by the same amount.

### `desk` (1 row): the shop's clock and notepad

| Field | Type | Notes |
|---|---|---|
| `date_today` | TEXT | `2026-08-31`, the official "today" |
| `notes` | TEXT | Shared notes (empty) |

**Why it matters for agents:** All agents use it as the official date, so overdue and due-soon checks match the scenario's date instead of today's real date.

## How the tables connect

```
tickets.invoice_id ──► invoices.id ──► invoices.vendor_id ──► vendors.id (lead_days)
tickets.lease_id   ──► leases.id
tickets.sku + size ──► inventory (sku, size)
tickets.sku        ──► pricing.sku
payments.ref_id    ──► invoices.id / leases.id  (based on payments.kind)
payments.account   ──► cash_accounts.name
desk.date_today    ──► used by every date check
```

Only `tickets → invoices` and `tickets → leases` are real foreign keys. The other links are by matching values, so tools must join them on purpose.

## MCP tools

All agents get their shop facts from `mcp_server/server.py` (`campus-customs`), which reads `data/campus_customs_new.db`. The backend never opens the database itself. There are 11 tools: 9 read-only tools the agents use, and 2 write tools that only the backend calls after a human acts (listed at the end of the table).

| Tool | Reads tables | Unlocks ticket | Why it's the right tool |
|---|---|---|---|
| `get_ticket_details(ticket_id)` | `tickets`, `desk`, `inventory`, `leases`, `invoices`, `vendors` | **101, 102, 103** (every ticket) | It's the Boss's first call on any ticket. In one call it returns the request, the requester's notes, the status, and the shop's date, and it follows the ticket's links. For 101 that's the product and invoice 501 (Bulldog Print Co). For 102 it's the Chapel Street lease, with rent due in 2 days. For 103 it's the hoodie SKU, size, and quantity. The Boss can then route the ticket to the right specialist. |
| `check_item_availability(sku, size, qty_needed)` | `inventory`, `pricing` | **101** (tee S) and **103** (20 hoodies M) | Both tickets depend on whether a specific size is in stock, and on cost vs. price. For 101 it shows 0 in S, a shortfall of 1, and $8 to restock. For 103 it shows 8 in M, a shortfall of 12, and $264 to restock, plus the $22 cost vs. $58 list price (a $36 margin). Accounting needs that margin to judge how big a bulk discount can be. Stock is tracked per size, which is why the tool takes a size. |
| `check_invoice_payment(invoice_id or vendor_id, or nothing for the full ledger)` | `invoices`, `vendors`, `payments`, `desk` | **101** (invoice 501) and **103** (reprint from the same vendor) | Any reprint goes through Bulldog Print Co, and vendors won't ship while a bill is unpaid. For 101 it shows invoice 501 as $840, unpaid, and 3 days overdue (based on `desk.date_today`), with `vendor_will_ship = false`. For 103, calling it with `vendor_id=1` shows the same block on the 12-hoodie reprint. Accounting knows the bill must be paid (with human approval) before any reprint, and the lead time is 5 days after that. |
| `list_tickets(status="open")` | `tickets`, `desk` | **all** (the board) | Gives the Boss the whole queue in one line per ticket, so a full run can loop over every open ticket without guessing ids. |
| `get_lease_details(lease_id?)` | `leases`, `payments`, `desk` | **102** (rent) | Returns the Chapel Street lease: $2,400 rent due 2026-09-02, **2 days** out, not overdue, no rent payments on record. Facilities can answer "when, how much, and has it been paid" from the database instead of the landlord's email. |
| `get_cash_balance(account?)` | `cash_accounts`, `invoices`, `vendors`, `payments`, `leases`, `desk` | **101, 102, 103** (anything that spends cash) | Shows $3,400 in checking **and** everything waiting on it (invoice 501 $840 plus rent $2,400 = $3,240), leaving **$160**. That's the cash squeeze across all three tickets, and Accounting can't judge one payment without seeing the others. |
| `check_cash_for_payment(amount, account="checking")` | `cash_accounts`, `desk` | **101, 102, 103** | Enforces the no-negative-balance rule before anyone recommends money out. $3,240 fits ($160 left), while $3,504 (adding the 12-hoodie reprint) is **$104 short**. It never moves money and always returns `requires_human_approval: true`. |
| `get_vendor_info(vendor_id? / specialty?)` | `vendors`, `invoices`, `payments`, `desk` | **101, 103** (reprints) | Lead times must come from the vendors table. Bulldog Print Co (apparel) takes 5 days (earliest 2026-09-05), but `will_ship = false` while invoice 501 is unpaid. Matching on specialty is how agents find the right vendor, since no column links SKUs to vendors. |
| `get_pricing(sku?, qty?, discount_pct?)` | `pricing`, `inventory` | **103** (bulk discount), **101** (PO cost) | Prices a discount quote from real cost and list price. For example, 20 hoodies at 15% off is $49.30 each, $986 total, $546 margin, not below cost, and the most it could be discounted before losing money is 62.1%. Accounting judges the discount and Inventory costs the PO with it. |
| `record_payment(kind, amount, approved_by, ref_id?, account?, payee?)` **(write, backend only)** | writes `payments`, `cash_accounts`, `invoices`, `leases`; reads `vendors`, `desk` | **101** (invoice 501), **102** (rent), POs | The only way money leaves the account, and only after a human clicks Approve. In one transaction it refuses an empty or agent approver, a negative balance, an overpaid or already-paid invoice, a rent amount that isn't the monthly rent, or a PO to a vendor with an unpaid invoice. Then it records the payment (`paid_at = desk.date_today`), lowers the balance, marks the invoice paid, or moves the lease's `next_due` forward a month. |
| `set_ticket_status(ticket_id, status)` **(write, backend only)** | writes `tickets` | **101, 102, 103** | Moves a ticket between `open` and `resolved` on the board when the team's call is final, or once every payment it needs is approved. |

## Agents

Built with PydanticAI in `backend/`. **Every agent runs on `gpt-6-luna` only** (`backend/config.py` refuses any other model). Calls go through Portkey's Responses API using `PORTKEY_API_KEY` from `.env`.

| Agent | File / prompt | Job | MCP tools | Tables it reaches (through MCP) | Output |
|---|---|---|---|---|---|
| Boss | `agents/boss.py` / `prompts/boss.md` | Reads the ticket, assigns work, investigates conflicts, makes the final call | `get_ticket_details`, `list_tickets` | `tickets`, `desk` (+ linked `inventory`, `leases`, `invoices`, `vendors` rows) | `TicketDecision` |
| Inventory | `agents/inventory.py` / `prompts/inventory.md` | Stock by SKU and size, shortfalls, restock POs and lead times | `get_ticket_details`, `check_item_availability`, `get_pricing`, `get_vendor_info` | `inventory`, `pricing`, `vendors`, `invoices`, `payments`, `desk` | `AgentReport` |
| Accounting | `agents/accounting.py` / `prompts/accounting.md` | Owed / paid / overdue, cash, margins, payment and PO requests for human approval | `get_ticket_details`, `check_invoice_payment`, `get_cash_balance`, `check_cash_for_payment`, `get_pricing`, `get_vendor_info` | `invoices`, `payments`, `vendors`, `cash_accounts`, `leases`, `pricing`, `desk` | `AgentReport` |
| Facilities | `agents/facilities.py` / `prompts/facilities.md` | Leases, rent, the shop space | `get_ticket_details`, `get_lease_details` | `leases`, `payments`, `desk` | `AgentReport` |
| Customer Service | `agents/customer_service.py` / `prompts/customer_service.md` | Understands the customer's need, gets facts from teammates, drafts the message | `get_ticket_details` | `tickets` (all other facts come from teammates) | `AgentReport` (`customer_message_draft`) |

Every prompt starts with Francisco's role text word for word, then adds that agent's tools and working steps. `prompts/team.md` is appended to every agent: the team roster, how to delegate, the facts rules, and the safety rules below. The structured types are in `backend/models.py`: `TicketDecision`, `AgentReport`, `Fact`, `PaymentRequest`, `PurchaseOrderDraft`, `PlannedAction`, `SafetyCheck`, `TicketResult`.

### Delegation (full connectivity)

- Every agent has an `ask_agent(agent, request)` tool and can delegate to **any** teammate, Boss included. The teammate runs its own loop and returns its structured report.
- **Loop guards** (enforced in `team.py`, not left to the model):
  - No asking yourself.
  - No asking an agent already upstream in the chain (prevents A→B→A loops).
  - Delegation depth of at most 3.
  - At most 8 agent runs per ticket (a ticket normally needs 2–4).
  - One shared usage budget per ticket: 40 model requests and 50 tool calls.
- One MCP server process is shared by the whole team for a run.

### Efficient routing (the Boss doesn't call everyone)

The Boss starts with the one agent who owns the ticket's main question, reads that report, and brings in the next agent only if a question is still open. Each request carries the facts the Boss already has (including `date_today`), so nobody looks them up twice.

| Ticket type | Start with | Then, only if needed | Usually not needed |
|---|---|---|---|
| `customer_order` (101) | Inventory: exact SKU/size in stock? | Accounting, if the order depends on an unpaid invoice or payment. Customer Service last, for the reply. | Facilities |
| `rent_notice` (102) | Facilities: confirm the lease, rent, and due date | Accounting: cash for rent alongside other bills, plus the payment request | Inventory, Customer Service |
| `price_override` (103) | Inventory: stock, plus vendor lead time and whether it will ship | Accounting: margin on specific discount options and cash for the restock. Customer Service last, for the reply. | Facilities |

Specialists finish their own answers with their own tools and only delegate when they're truly blocked. Questions they can't answer go in `recommendations` for the Boss to route. For example, Inventory reports the unpaid invoice it sees in `get_vendor_info` instead of asking Accounting to confirm it. Customer Service is asked once, at the end, with the decision and the confirmed facts.

### Audit trail: `output/audit_trail.json`

Every run (`run_team.py --ticket N`, `--all`, or `--ask AGENT "question"`) appends one record:

- **Run:** `run_id`, `kind`, `subject`, `ticket_id`, `model_configured`, `models_used` (as reported by the API), `started_at`, `finished_at`, `duration_ms`, `status`, `error`, `usage_totals`, counts of agent runs, delegations and tool calls, the `safety_check`, and the final `result`.
- **`agent_runs`:** one entry per agent run, with id, parent run, depth, chain, task, start time, duration, status, loop steps, usage, and output.
- **`events`:** a time-ordered log with seq, timestamp, and elapsed ms, each tagged with agent, depth and **loop step**. Event kinds: `agent_start`, `loop_step`, `model_response` (model name, tokens, finish reason), `tool_call` (tool and arguments), `tool_result` (what the tool returned), `retry`, `delegate`, `delegate_refused`, `agent_end`, `safety_check`.
- **Errors:** failed runs are saved too, with `status: "error"` and the error message.

## Backend routes (`backend/main.py`)

Start from `backend/` with the HW5 venv active: `uvicorn main:app --reload --port 8000` (base URL `http://127.0.0.1:8000`). All shop facts and writes go through the MCP server.

- `GET /api/tickets`: lists all 3 tickets with `open`/`resolved` status, whether one is running, pending approvals, and the team's latest decision.
- `POST /api/tickets/{ticket_id}/run`: starts the agent team on a ticket in the background and returns a `run_id` at once (409 if a run is already going, 404 if the ticket doesn't exist).
- `GET /api/runs/{run_id}`: shows whether a run is `running`, `ok`, or `error`, and the Boss's decision and safety check when it's done.
- `GET /api/events?since=<seq>&ticket_id=&run_id=`: returns recent agent events for the live board: who started, who asked whom, which tools they used with what arguments, what tools returned, what each agent said, and run, approval, and reset events. Poll with `since=last_seq`.
- `GET /api/payments/pending`: lists the payments and purchase orders the team prepared that are waiting for a human. Requests for a bill that's already paid are closed as `covered` first.
- `POST /api/payments/{approval_id}/approve` (body `{"approved_by": "<human>", "confirm": true}`): records the payment only after a human clicks Approve, then returns the new balance. If other tickets asked for the same bill (e.g. invoice 501 for #101 and #103), their requests are closed as `covered`, so a bill is never paid twice.
- `GET /api/cash`: returns the current checking balance from `cash_accounts` (with `date_today` and upcoming obligations).
- `POST /api/reset`: resets `campus_customs_new.db` to the original values and clears board state, for a fresh run (409 while a run is going).
- `GET /api/health`: health check (model, number of MCP tools, current run).

**When a ticket becomes resolved:** as soon as a team run finishes (the Boss made its call), the backend marks it `resolved`. Payments and purchases the decision asked for stay in the approval queue until a human approves them. A failed run leaves the ticket `open`.

## Dashboard (`frontend/`, React + Vite + TypeScript)

Start it with `npm run dev` in `frontend/` and open http://localhost:5173 (`?ticket=103` opens a specific ticket). It calls the backend at http://localhost:8000, which allows that origin through CORS. Design choices and the reasons for them are in `output/design.md`.

| Part | What it shows | Routes it uses |
|---|---|---|
| Header | Greeting, `desk.date_today`, **live checking balance** (rolls and flashes when cash moves, plus bills waiting and what's left after them), and **↺ Fresh run** (reset, with a confirmation) | `GET /api/cash`, `POST /api/reset` |
| Ticket board | All 3 tickets with Open / On it… / Resolved, the last call, signatures waiting, and **Send in the team** | `GET /api/tickets`, `POST /api/tickets/{id}/run` |
| Team room | The five agents as characters (Coach Dan, Stacks, Penny, Keys, Sunny) with icons and fun lines. Wires light up and show "from Coach Dan ×2" when someone delegates. Avatars hop while working, tilt while waiting, and get a ✓ when done. | `GET /api/events` (polled every second) |
| What each agent did | One compact card per agent that worked: tools, who asked them, time, and last words | `GET /api/events` |
| Play-by-play | Handoffs with the full request, tool calls with arguments (click for the result), what each agent said, the safety check, and approvals | `GET /api/events` |
| Needs your signature | One card per **bill** (duplicate requests are merged), **Sign** opens a sheet with balance before/after, a required name, and an "I'm a human" checkbox. Refusals show the reason. | `GET /api/payments/pending`, `POST /api/payments/{id}/approve` |
| The call | Coach Dan's decision, blockers, Sunny's draft to the customer, and the safety check | `GET /api/tickets` (`last_run`) |

## Problem 9 run (reset → 3 tickets → human signatures)

- **Reset** at 12:14:55: the working db matched the original. Checking started at **$3,400.00** with 0 payments.
- **Runs** (appended to `output/audit_trail.json`): `run-20261006-121503-da0271` (#101), `run-20261006-121514-db4ca6` (#102), `run-20261006-121519-4b213b` (#103), all on `gpt-6-luna`. Their model replies were served from Portkey's cache: the prompts and db state were identical to the fresh 12:02–12:07 runs, which are also in the audit trail. Tool calls ran live against the db.

| Ticket | Agents | Decision | Cash |
|---|---|---|---|
| #101 Bulldog tee | Coach Dan → Stacks → Penny → Sunny | On hold: size S out of stock, vendor blocked by unpaid invoice 501 | $0 (its invoice request was covered by #103's payment) |
| #102 Rent due | Coach Dan → Keys → Penny | Approved with conditions: rent $2,400 prepared for approval | $0: rent still unsigned, and it can't fit ($2,296 − $2,400 = −$104) |
| #103 Bulk hoodie discount | Coach Dan → Stacks → Penny → Sunny | Needs a human call: Penny priced 5/10/15% options, no discount invented | −$840 (invoice 501) − $264 (12-hoodie PO), both signed by Francisco Udave |

- **Ending checking: $2,296.00** = $3,400.00 − $840.00 − $264.00, matching `cash_accounts`.
- **Reports:** `output/desk_tickets.html` (Actual + Cash tabs), `output/resolved_tickets.json`, and `output/resolved_board.html` (board screenshots). All three are regenerated from the real data by `backend/build_reports.py`.

## Safety rules

These rules are in every agent's prompt (`prompts/team.md`), and the parts marked **code** are also enforced by the code, so they don't depend on the model.

1. **`desk.date_today` is today.** Every overdue and due-soon check uses it, not the real calendar (**code**: every MCP tool returns `date_today` and computes `days_overdue` / `days_until_due` from it).
2. **Vendor lead times come from the `vendors` table** (**code**: `get_vendor_info` computes `earliest_delivery_if_ordered_today` from `lead_days`).
3. **Vendors won't ship new product while they have an open unpaid invoice** (**code**: `will_ship` / `vendor_will_ship` is false while any invoice is unpaid). Agents must report it as a blocker, and Accounting must say the order can't proceed.
4. **Every payment needs human approval** (**code**: agents can't see `record_payment` or `set_ticket_status`, because their tool allowlists leave them out; `PaymentRequest.requires_human_approval` can only be `true`; the approve route requires `confirm: true` and a human `approved_by`; `record_payment` rejects agent names). Agents never say a payment was made unless the `payments` table shows it.
5. **No negative balances, and no payment the balance can't cover** (**code**: after every ticket, `team.py` re-checks the combined `payment_requests` total through `check_cash_for_payment`, and flags `within_balance: false` with the shortfall so a human chooses).
6. **Only cash goes out; no revenue.** Sales and quotes never count toward the balance (**code**: `get_cash_balance` only subtracts obligations and never adds sales).
7. **Before a full run, reset the db to its original values** (**code**: `run_team.py --all` runs `reset_db.py` first, which copies `campus_customs.db` over `campus_customs_new.db` and checks the hashes match). The original database is never written.
8. **Only `gpt-6-luna`, to keep costs low** (**code**: `build_model()` raises an error for any other model; the audit records `models_used` on every run to prove it).
9. **Facts only from the MCP server.** No invented stock, prices, dates or balances, and every fact in a report names its source tool. The backend has no database access that bypasses the MCP server.
10. **Never make up a discount.** The database has no discount policy. A discount can only be a specific option Accounting priced with `get_pricing` (margin and below-cost check), and choosing one is a human decision (`approve_with_conditions` or `escalate_to_human`).
11. **Use resources efficiently.** Delegate only to the agent who owns the missing fact (see *Efficient routing*). **Code:** at most 8 agent runs, 40 model requests, and 50 tool calls per ticket.
12. **One bill, one payment.** If several tickets request the same bill, signing it once closes the others as `covered` (**code**: `board.cover_duplicates`; `record_payment` also refuses an already-paid invoice).

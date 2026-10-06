# Campus Customs Agent Team · HW5

Francisco Udave · AI Foundations for Managers (Yale SOM)

A five-agent team that runs Campus Customs from a ticket board. **Coach Dan** (Boss), **Stacks** (Inventory), **Penny** (Accounting), **Keys** (Facilities), and **Sunny** (Customer Service) work tickets like customer orders, rent notices, and discount requests. They get every shop fact from an **MCP server** over a SQLite database, run inside a **FastAPI** backend, and are watched and approved by humans on a **React** board. Every agent runs on `gpt-6-luna`, and no money moves without a human signature.

```
React board (5173)  ──►  FastAPI + PydanticAI team (8000)  ──►  MCP server  ──►  data/campus_customs_new.db
```

## Layout

```
hw5/
├── AI_prompts.md            every prompt for Problems 1–11, with summaries
├── requirements.txt         Python packages (backend + MCP server)
├── .env.example             copy to .env and add PORTKEY_API_KEY
├── .mcp.json                lets Claude Code connect to the MCP server
├── data/
│   ├── campus_customs.db       original, never modified (the reset source)
│   └── campus_customs_new.db   working copy the app reads and writes
├── mcp_server/              server.py (11 tools) + README.md
├── backend/                 main.py (FastAPI), models.py, prompts/, agents/, team.py, …
├── frontend/                React + Vite + TypeScript board
└── output/                  harness.md, mcp_smoke.json, desk_tickets.html, design.md,
                             resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt
```

The working copy is committed in its **after-the-run** state (checking $2,296 after two human-signed payments) so it matches the reports in `output/`. Reset it before your own run (step 3).

## Run it

You need Python 3.11+ (built on 3.13), Node 20+, and a Portkey key.

### 1. Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 2. Add your key

```bash
cp .env.example .env        # then put your PORTKEY_API_KEY in .env
```

`.env` is git-ignored; the real key is never committed.

### 3. Copy the original database to the working copy (clean run)

Whenever you want a clean run, copy the original over the working copy:

```bash
python backend/reset_db.py
```

This does the same as `cp data/campus_customs.db data/campus_customs_new.db` and checks that the hashes match. The original file is only ever read.

### 4. Start the MCP server

The backend **starts its own copy automatically** (stdio), so for the app you can skip this step. To run it by hand, or for an MCP client:

```bash
python mcp_server/server.py            # stdio
python mcp_server/server.py --http     # HTTP at http://127.0.0.1:8001/mcp
```

To make the backend use your HTTP server instead, set `CAMPUS_MCP_URL=http://127.0.0.1:8001/mcp` in `.env`. Claude Code picks up the server from `.mcp.json` (run it with the venv active so `python` has `fastmcp`).

### 5. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Check http://localhost:8000/api/health. It should report `gpt-6-luna` and 11 MCP tools. The backend allows the board's origin `http://localhost:5173` through CORS.

### 6. Start the React board

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. It shows the ticket board, the live team room (who's talking to whom), the play-by-play, the call, what each agent did, "Needs your signature", and the live checking balance.

### 7. Full three-ticket run (always reset first)

1. **Reset the database.** Click **↺ Fresh run** on the board, or run `python backend/reset_db.py` (or `POST /api/reset`). Checking goes back to **$3,400**, and all tickets go back to open.
2. On the board, pick **#101**, then **#102**, then **#103**, and click **Send in the team** for each. One run happens at a time.
3. Sign any payments you approve under **Needs your signature**. Agents only prepare them, and the backend refuses anything that would overdraw checking.

You can also run all three from the terminal with `python backend/run_team.py --all`, which resets first. To ask one agent a question: `python backend/run_team.py --ask inventory "How many M hoodies?"`.

### 8. Rebuild the reports (optional)

```bash
cd backend
python build_reports.py      # desk_tickets.html (tickets + Cash), resolved_tickets.json, resolved_board.html
python build_reflection.py   # Reflections tab
```

## API routes

| Route | What it does |
|---|---|
| `GET /api/tickets` | All tickets, open or resolved, with the latest decision |
| `POST /api/tickets/{id}/run` | Run the agent team on a ticket |
| `GET /api/runs/{run_id}` | Status and result of one run |
| `GET /api/events?since=` | Live agent events: what they said, tools used, handoffs |
| `GET /api/payments/pending` | Payments and POs waiting for a human |
| `POST /api/payments/{id}/approve` | A human approves one payment (`{"approved_by": "...", "confirm": true}`) |
| `GET /api/cash` | Current checking balance from `cash_accounts` |
| `POST /api/reset` | Reset the working database to the original |

## Safety rules (enforced in code, not just prompts)

- `desk.date_today` (2026-08-31) is "today" for every date check.
- Vendor lead times come from the `vendors` table.
- Vendors won't ship while they have an unpaid invoice.
- Only a human can approve a payment: agents have no write tools, and approvals need a human name plus `confirm: true`.
- No negative balances: payments are checked against the balance inside one database transaction.
- Only cash goes out; sales revenue is never counted. One bill is paid once.
- Only `gpt-6-luna`, capped at 8 agent runs, 40 model calls, and 50 tool calls per ticket.

The full details (tables, tools, agents, routes, dashboard, and rules) are in `output/harness.md`.

"""Run the Campus Customs agent team from the command line.

    python run_team.py --ticket 101                  # Boss resolves one ticket
    python run_team.py --all                         # reset the db, then resolve every open ticket
    python run_team.py --ask inventory "How many M hoodies are in stock?"

Every run is appended to ../output/audit_trail.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import board  # noqa: E402
from agents import ROSTER  # noqa: E402
from reset_db import reset_working_db  # noqa: E402
from team import Team  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Campus Customs agent team")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket", type=int, help="ticket id for the Boss to resolve")
    group.add_argument("--all", action="store_true", help="full run: reset the db, then resolve every open ticket")
    group.add_argument("--ask", nargs=2, metavar=("AGENT", "QUESTION"), help=f"ask one agent: {', '.join(ROSTER)}")
    args = parser.parse_args()

    if args.all:
        reset_working_db()

    async with Team() as team:
        if args.ask:
            agent, question = args.ask
            if agent not in ROSTER:
                parser.error(f"unknown agent {agent!r}")
            output = await team.ask(agent, question)
            print(json.dumps(output.model_dump(mode="json"), indent=2))
            return 0

        if args.all:
            board_now = await team._call("list_tickets", {"status": "open"})
            ticket_ids = [t["id"] for t in board_now["tickets"]]
        else:
            ticket_ids = [args.ticket]

        for ticket_id in ticket_ids:
            print(f"\n=== Ticket {ticket_id} ===", flush=True)
            result = await team.resolve_ticket(ticket_id)
            # Same bookkeeping as the board's run route: the ticket is resolved and any
            # payments or POs wait on the board's "Needs your signature" for a human.
            queued = board.record_decision(result)
            await team._call("set_ticket_status", {"ticket_id": ticket_id, "status": "resolved"})
            print(json.dumps(result.model_dump(mode="json"), indent=2), flush=True)
            print(f"Ticket {ticket_id} resolved: {result.decision.decision}. "
                  f"{len(queued)} payment(s)/PO(s) waiting for a human signature on the board.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

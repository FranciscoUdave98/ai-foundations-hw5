"""Boss: reads each ticket, assigns work, combines findings, and makes the final call."""

from agents.base import build_agent
from models import TicketDecision

NAME = "boss"
# Coordinates rather than doing specialist work, so it only sees the board.
TOOLS = ("get_ticket_details", "list_tickets")


def build(mcp):
    return build_agent(NAME, TicketDecision, TOOLS, mcp)

"""Facilities: the shop space: leases, rent, and landlord questions."""

from agents.base import build_agent
from models import AgentReport

NAME = "facilities"
TOOLS = ("get_ticket_details", "get_lease_details")


def build(mcp):
    return build_agent(NAME, AgentReport, TOOLS, mcp)

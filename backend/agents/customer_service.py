"""Customer Service: understands the customer's need and drafts the message."""

from agents.base import build_agent
from models import AgentReport

NAME = "customer_service"
# Gets the request from the ticket; every fact it promises comes from a teammate.
TOOLS = ("get_ticket_details",)


def build(mcp):
    return build_agent(NAME, AgentReport, TOOLS, mcp)

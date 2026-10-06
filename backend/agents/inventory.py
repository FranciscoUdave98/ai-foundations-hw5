"""Inventory: stock by SKU and size, shortfalls, and restock options."""

from agents.base import build_agent
from models import AgentReport

NAME = "inventory"
TOOLS = ("get_ticket_details", "check_item_availability", "get_pricing", "get_vendor_info")


def build(mcp):
    return build_agent(NAME, AgentReport, TOOLS, mcp)

"""Accounting: cash, invoices, margins, and payments/POs prepared for human approval."""

from agents.base import build_agent
from models import AgentReport

NAME = "accounting"
TOOLS = (
    "get_ticket_details",
    "check_invoice_payment",
    "get_cash_balance",
    "check_cash_for_payment",
    "get_pricing",
    "get_vendor_info",
)


def build(mcp):
    return build_agent(NAME, AgentReport, TOOLS, mcp)

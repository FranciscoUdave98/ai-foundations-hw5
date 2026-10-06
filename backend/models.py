"""Structured data the agents hand to each other and to the humans."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
SPECIALISTS: tuple[AgentName, ...] = ("inventory", "accounting", "facilities", "customer_service")


class Fact(BaseModel):
    """One checked fact, with the MCP tool (or teammate) it came from."""

    label: str = Field(description="What the fact is, e.g. 'CC-TEE-WHITE size S on hand'.")
    value: str = Field(description="The value exactly as the tool returned it.")
    source: str = Field(description="MCP tool name that returned it, or 'agent:<name>' if a teammate reported it.")


class PaymentRequest(BaseModel):
    """A payment an agent prepares. Only a human can approve or send it."""

    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int | None = Field(description="invoices.id for invoice, leases.id for rent, None for a new PO.")
    payee: str
    amount: float = Field(gt=0)
    account: str = "checking"
    reason: str
    requires_human_approval: Literal[True] = True


class PurchaseOrderDraft(BaseModel):
    """A restock order an agent prepares. Never placed without human approval."""

    vendor_id: int
    vendor_name: str
    sku: str
    size: str
    qty: int = Field(gt=0)
    unit_cost: float
    total_cost: float
    lead_days: int
    earliest_delivery: str | None = Field(description="desk.date_today + lead_days, only if the vendor will ship.")
    blocked_by: list[str] = Field(default_factory=list, description="Why it can't be placed yet, e.g. 'invoice 501 unpaid'.")


class AgentReport(BaseModel):
    """What a specialist sends back to whoever asked."""

    agent: AgentName
    answer: str = Field(description="Direct answer to the request, in plain words.")
    facts: list[Fact] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list, description="Anything that stops the work from going ahead.")
    recommendations: list[str] = Field(default_factory=list)
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrderDraft] = Field(default_factory=list)
    customer_message_draft: str | None = Field(default=None, description="Customer Service only: the drafted message.")
    consulted: list[AgentName] = Field(default_factory=list, description="Teammates asked while preparing this report.")


class PlannedAction(BaseModel):
    owner: AgentName | Literal["human"]
    action: str
    status: Literal["ready", "blocked", "awaiting_human_approval"]


class TicketDecision(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    ticket_type: str
    decision: Literal["approve", "approve_with_conditions", "hold", "decline", "escalate_to_human"]
    final_call: str = Field(description="One or two sentences: what happens with this ticket.")
    reasoning: str
    assigned_agents: list[AgentName]
    findings: list[Fact] = Field(default_factory=list)
    conflicts_investigated: list[str] = Field(default_factory=list)
    actions: list[PlannedAction] = Field(default_factory=list)
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrderDraft] = Field(default_factory=list)
    customer_message: str | None = None
    blockers: list[str] = Field(default_factory=list)


class SafetyCheck(BaseModel):
    """Checks the code (not the model) runs on every decision before a human sees it."""

    payment_total: float
    cash_balance: float | None
    balance_after: float | None
    within_balance: bool
    all_payments_need_human_approval: bool
    payments_recorded_in_db: int = Field(description="Rows in payments after the run. Agents can't write payments.")
    notes: list[str] = Field(default_factory=list)


class TicketResult(BaseModel):
    run_id: str
    ticket_id: int
    model: str
    duration_ms: int
    decision: TicketDecision
    safety: SafetyCheck

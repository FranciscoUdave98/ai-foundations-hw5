"""The Campus Customs agent team: runs agents, routes delegations, and audits everything.

Usage:
    async with Team() as team:
        result = await team.resolve_ticket(101)        # Boss resolves a ticket end-to-end
        report = await team.ask("inventory", "...")    # ask one agent directly

All five agents share one MCP connection. Every loop step (model request, model
response, tool call, tool result, delegation) is logged to output/audit_trail.json.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import RunUsage

from agents import ROSTER
from agents.base import TeamDeps
from audit import AuditRecorder
from config import MAX_AGENT_RUNS_PER_TICKET, MAX_DELEGATION_DEPTH, MODEL_NAME, USAGE_LIMITS, build_mcp_toolset
from models import AgentName, SafetyCheck, TicketDecision, TicketResult


def _usage_dict(usage: RunUsage) -> dict:
    return {"requests": usage.requests, "tool_calls": usage.tool_calls,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def _args(part: ToolCallPart) -> Any:
    if isinstance(part.args, str):
        try:
            return json.loads(part.args)
        except json.JSONDecodeError:
            return part.args
    return part.args


class Team:
    def __init__(self) -> None:
        self.mcp = build_mcp_toolset()
        self.agents: dict[str, Agent] = {name: module.build(self.mcp) for name, module in ROSTER.items()}

    async def __aenter__(self) -> Team:
        await self.mcp.__aenter__()  # one MCP server process for the whole team
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.mcp.__aexit__(*exc)

    # ---- the agent loop -------------------------------------------------

    async def run_agent(self, name: AgentName, task: str, audit: AuditRecorder,
                        parent: TeamDeps | None, usage: RunUsage) -> Any:
        """Run one agent's loop (model -> tools -> model ... -> output), logging every step."""
        depth = parent.depth + 1 if parent else 0
        chain = (*parent.chain, name) if parent else (name,)
        run_id = audit.start_agent(name, task, parent.agent_run_id if parent else None, depth, chain)
        deps = TeamDeps(team=self, audit=audit, agent=name, agent_run_id=run_id, depth=depth, chain=chain)
        tag = {"agent": name, "agent_run_id": run_id, "depth": depth}
        step = 0
        before = _usage_dict(usage)
        try:
            async with self.agents[name].iter(task, deps=deps, usage=usage, usage_limits=USAGE_LIMITS) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        step += 1
                        audit.event("loop_step", loop_step=step, **tag)
                        for part in node.request.parts:
                            if isinstance(part, ToolReturnPart):
                                audit.event("tool_result", loop_step=step, tool=part.tool_name,
                                            tool_call_id=part.tool_call_id, result=part.content, **tag)
                            elif isinstance(part, RetryPromptPart):
                                audit.event("retry", loop_step=step, tool=part.tool_name,
                                            reason=part.content, **tag)
                    elif Agent.is_call_tools_node(node):
                        response = node.model_response
                        if response.model_name:
                            audit.models_seen.add(response.model_name)
                        audit.event(
                            "model_response", loop_step=step, model=response.model_name,
                            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                            finish_reason=response.finish_reason,
                            text=" ".join(p.content for p in response.parts if isinstance(p, TextPart)) or None,
                            **tag,
                        )
                        for part in response.parts:
                            if isinstance(part, ToolCallPart):
                                audit.event("tool_call", loop_step=step, tool=part.tool_name,
                                            tool_call_id=part.tool_call_id, args=_args(part), **tag)
                output = run.result.output
        except Exception as exc:
            audit.finish_agent(run_id, status="error", loop_steps=step, error=f"{type(exc).__name__}: {exc}")
            raise
        after = _usage_dict(usage)
        audit.finish_agent(run_id, status="ok", loop_steps=step, output=output,
                           usage={k: after[k] - before[k] for k in after})  # includes its delegations
        return output

    # ---- delegation -------------------------------------------------------

    async def delegate(self, ctx: RunContext[TeamDeps], target: str, request: str) -> dict:
        """Called by the ask_agent tool. Enforces the loop guards, then runs the teammate."""
        deps = ctx.deps
        tag = {"agent": deps.agent, "agent_run_id": deps.agent_run_id, "depth": deps.depth}
        refusal = None
        if target not in self.agents:
            refusal = f"Unknown agent '{target}'. Choose from: {', '.join(self.agents)}."
        elif target == deps.agent:
            refusal = "You can't delegate to yourself. Use your own tools."
        elif target in deps.chain:
            refusal = (f"{target} is already working upstream on this request "
                       f"({' -> '.join(deps.chain)}). Answer with the facts you have and list what is missing.")
        elif deps.depth + 1 > MAX_DELEGATION_DEPTH:
            refusal = f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached. Answer with what you have."
        elif deps.audit.agent_run_count >= MAX_AGENT_RUNS_PER_TICKET:
            refusal = f"Team budget of {MAX_AGENT_RUNS_PER_TICKET} agent runs reached. Answer with what you have."
        if refusal:
            deps.audit.event("delegate_refused", to=target, request=request, reason=refusal, **tag)
            return {"error": refusal}

        deps.audit.event("delegate", to=target, request=request, **tag)
        try:
            output = await self.run_agent(target, request, deps.audit, deps, ctx.usage)
        except UsageLimitExceeded:
            raise  # the ticket's budget is spent: stop the whole run
        except Exception as exc:  # a failing teammate shouldn't crash the caller's decision
            return {"error": f"{target} failed: {type(exc).__name__}: {exc}"}
        return output.model_dump(mode="json")

    # ---- entry points --------------------------------------------------

    def new_ticket_audit(self, ticket_id: int, listener=None) -> AuditRecorder:
        return AuditRecorder("ticket", f"Resolve ticket {ticket_id}", MODEL_NAME, ticket_id=ticket_id, listener=listener)

    async def resolve_ticket(self, ticket_id: int, audit: AuditRecorder | None = None) -> TicketResult:
        """The Boss resolves one ticket end-to-end; the run is appended to the audit trail."""
        audit = audit or self.new_ticket_audit(ticket_id)
        usage = RunUsage()
        task = (f"Resolve ticket {ticket_id} from the Campus Customs board. Read it, assign the work to the "
                f"right teammates, combine their findings, and make the final call.")
        result = None
        try:
            decision: TicketDecision = await self.run_agent("boss", task, audit, None, usage)
            safety = await self._safety_check(decision, audit)
            result = TicketResult(run_id=audit.run_id, ticket_id=ticket_id, model=MODEL_NAME,
                                  duration_ms=audit.elapsed_ms(), decision=decision, safety=safety)
            audit.save(audit.record(status="ok", result=result, usage=_usage_dict(usage)))
            return result
        except Exception as exc:
            audit.save(audit.record(status="error", error=f"{type(exc).__name__}: {exc}", usage=_usage_dict(usage)))
            raise

    async def ask(self, agent: AgentName, question: str) -> Any:
        """Ask one agent directly (it can still delegate). Also audited."""
        audit = AuditRecorder("question", question, MODEL_NAME)
        usage = RunUsage()
        try:
            output = await self.run_agent(agent, question, audit, None, usage)
            audit.save(audit.record(status="ok", result=output, usage=_usage_dict(usage)))
            return output
        except Exception as exc:
            audit.save(audit.record(status="error", error=f"{type(exc).__name__}: {exc}", usage=_usage_dict(usage)))
            raise

    # ---- guardrails (code, not the model) ------------------------------

    async def _call(self, tool: str, args: dict) -> dict:
        result = await self.mcp.direct_call_tool(tool, args)
        return result if isinstance(result, dict) else json.loads(result)

    async def _safety_check(self, decision: TicketDecision, audit: AuditRecorder) -> SafetyCheck:
        """Re-check the Boss's payment requests against the db, through the MCP server."""
        total = round(sum(p.amount for p in decision.payment_requests), 2)
        notes: list[str] = []
        if total > 0:
            cash = await self._call("check_cash_for_payment", {"amount": total})
            balance, after, ok = cash["balance"], cash["balance_after"], cash["can_pay"]
            if not ok:
                notes.append(f"Requested payments (${total:,.2f}) exceed the balance by ${cash['shortfall']:,.2f}. "
                             f"A human must choose which to approve.")
        else:
            cash = await self._call("get_cash_balance", {"account": "checking"})
            balance, after, ok = cash["total_balance"], cash["total_balance"], True
        ledger = await self._call("check_invoice_payment", {})
        if ledger["payment_count"]:
            notes.append(f"{ledger['payment_count']} payment(s) are recorded in the db; verify each had human approval.")
        notes.append("Payments and POs are drafts only; nothing is paid until a human approves.")
        check = SafetyCheck(
            payment_total=total, cash_balance=balance, balance_after=after, within_balance=ok,
            all_payments_need_human_approval=all(p.requires_human_approval for p in decision.payment_requests),
            payments_recorded_in_db=ledger["payment_count"], notes=notes,
        )
        audit.safety = check.model_dump(mode="json")
        audit.event("safety_check", agent="system", **audit.safety)
        return check

"""What every agent on the team shares: deps, the delegation tool, and the builder.

Each agent gets:
- its own prompt (prompts/<name>.md) plus the shared team rules (prompts/team.md)
- only the MCP tools its role needs (a filtered view of the one MCP connection)
- ask_agent, so it can delegate work to any teammate
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset

from audit import AuditRecorder
from config import PROMPTS_DIR, build_model
from models import AgentName

if TYPE_CHECKING:
    from team import Team


@dataclass
class TeamDeps:
    """Passed into every agent run: who is running, who asked, and where to log."""

    team: Team
    audit: AuditRecorder
    agent: AgentName
    agent_run_id: str
    depth: int
    chain: tuple[AgentName, ...]


def load_instructions(name: str) -> str:
    role = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    team = (PROMPTS_DIR / "team.md").read_text(encoding="utf-8").strip()
    return f"{role}\n\n{team}"


async def ask_agent(ctx: RunContext[TeamDeps], agent: AgentName, request: str) -> dict[str, Any]:
    """Delegate a task or question to a teammate and get their report back.

    agent: "boss", "inventory", "accounting", "facilities", or "customer_service".
    request: a specific, self-contained ask. Include the ticket id and every
    detail they need (SKU, size, qty, invoice id, amounts), and say exactly
    what you need back. Teammates can't see your conversation.
    """
    return await ctx.deps.team.delegate(ctx, agent, request)


def build_agent(name: AgentName, output_type: type, tool_names: tuple[str, ...], mcp: MCPToolset) -> Agent[TeamDeps, Any]:
    allowed = frozenset(tool_names)
    return Agent(
        build_model(),
        name=name,
        deps_type=TeamDeps,
        output_type=output_type,
        instructions=load_instructions(name),
        tools=[ask_agent],
        toolsets=[mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)],
        retries=2,
    )

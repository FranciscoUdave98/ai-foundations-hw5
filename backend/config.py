"""Shared settings for the Campus Customs agent team.

One place for the model, the Portkey connection, the MCP connection, and the
cost limits. Importing this module never calls the API or prints the key.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from openai import AsyncOpenAI
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

BACKEND_DIR = Path(__file__).resolve().parent
HW_DIR = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
OUTPUT_DIR = HW_DIR / "output"
AUDIT_PATH = OUTPUT_DIR / "audit_trail.json"

# The backend never opens the database itself: every shop fact comes from the
# MCP server, which reads the working copy. These paths are only for reset_db.py.
DB_ORIGINAL = HW_DIR / "data" / "campus_customs.db"
DB_WORKING = HW_DIR / "data" / "campus_customs_new.db"

MCP_SERVER_SCRIPT = HW_DIR / "mcp_server" / "server.py"
MCP_URL = os.getenv("CAMPUS_MCP_URL")  # set to http://127.0.0.1:8001/mcp to use a running HTTP server

# Every agent runs on Luna and nothing else, to keep costs low.
MODEL_NAME = "gpt-6-luna"
ALLOWED_MODELS = frozenset({MODEL_NAME})
PORTKEY_URL = "https://api.portkey.ai/v1"

# Cost and loop guards for one ticket. Delegated runs share the ticket's usage,
# so these caps cover the whole team, not each agent.
USAGE_LIMITS = UsageLimits(request_limit=40, tool_calls_limit=50)
MAX_DELEGATION_DEPTH = 3       # boss (0) -> specialist (1) -> teammate (2) -> teammate (3)
MAX_AGENT_RUNS_PER_TICKET = 8  # boss + every delegation; a ticket normally needs 2-4


def load_api_key() -> str:
    """Read the Portkey key from .env (HW5/ first, then the course folder). Never printed."""
    load_dotenv(HW_DIR / ".env", override=False)
    load_dotenv(HW_DIR.parent / ".env", override=False)
    key = os.getenv("PORTKEY_API_KEY") or os.getenv("PORTKEY_PAI_KEY")
    if not key:
        raise RuntimeError("Missing PORTKEY_API_KEY in .env")
    return key


def build_model(name: str = MODEL_NAME) -> OpenAIResponsesModel:
    """Luna through Portkey's Responses API (chat completions rejects tools + reasoning on gpt-6-luna)."""
    if name not in ALLOWED_MODELS:
        raise ValueError(f"Model {name!r} is not allowed. Agents may only use {MODEL_NAME}.")
    key = load_api_key()
    client = AsyncOpenAI(
        api_key=key,
        base_url=PORTKEY_URL,
        default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(name, provider=OpenAIProvider(openai_client=client))


def build_mcp_toolset() -> MCPToolset:
    """Connection to the Campus Customs MCP server (stdio by default, HTTP if CAMPUS_MCP_URL is set)."""
    if MCP_URL:
        return MCPToolset(MCP_URL, id="campus-customs")
    transport = StdioTransport(command=sys.executable, args=[str(MCP_SERVER_SCRIPT)], cwd=str(MCP_SERVER_SCRIPT.parent))
    return MCPToolset(Client(transport), id="campus-customs")

# MCP Client — manages all 5 server connections
#
# startup()         : spawn each server (sys.executable, repo-root cwd, inherited env),
#                     open a ClientSession per server, discover and index tools.
# list_all_tools()  : aggregated tool definitions (used by system_prompt.py).
# call_tool(t, a)   : route a tool call to its owning server's session (graceful on failure).
# status()          : connection status per configured server (for GET /api/status).
# shutdown()        : close all sessions / subprocesses.
#
# NOTE: AsyncExitStack must be entered (startup) and closed (shutdown) in the SAME
# task — hang these off the FastAPI lifespan, not ad-hoc calls.
import sys
import os
import json
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "mcp_config.json")


def _configured_servers() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)["mcpServers"]


class MCPManager:
    def __init__(self):
        self._stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}   # server name -> session
        self.tool_to_server: dict[str, str] = {}       # tool name -> server name
        self.tools: list = []                          # aggregated tool definitions

    async def startup(self) -> None:
        # `python -m servers.x.server` + `from shared...` need the repo root importable.
        env = os.environ.copy()
        env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")

        for name, conf in _configured_servers().items():
            try:
                params = StdioServerParameters(
                    command=sys.executable,   # NOT the config's bare "python"
                    args=conf["args"],
                    env=env,                  # inherit dotenv-loaded vars
                    cwd=REPO_ROOT,
                )
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.sessions[name] = session
                for tool in (await session.list_tools()).tools:
                    self.tool_to_server[tool.name] = name
                    self.tools.append(tool)
            except Exception as e:
                # Graceful degradation: a failed server must not take down the others.
                print(f"[mcp] failed to start server '{name}': {e}", file=sys.stderr)

    def list_all_tools(self) -> list:
        """All tool definitions across connected servers (raw MCP Tool objects)."""
        return self.tools

    def tools_by_server(self) -> dict[str, list[str]]:
        """{server: [tool names]} — the shape build_system_prompt() expects."""
        grouped: dict[str, list[str]] = {}
        for tool, server in self.tool_to_server.items():
            grouped.setdefault(server, []).append(tool)
        return grouped

    async def call_tool(self, tool: str, args: dict) -> Any:
        """Route a tool call to its owning server's session; degrade gracefully."""
        server = self.tool_to_server.get(tool)
        if server is None:
            return {"error": f"unknown tool: {tool}"}
        try:
            return await self.sessions[server].call_tool(tool, args)
        except Exception as e:
            return {"error": f"{server}.{tool} failed: {e}"}

    def status(self) -> dict:
        """Per-server connection status for the dashboard's green/red dots."""
        return {
            name: ("connected" if name in self.sessions else "down")
            for name in _configured_servers()
        }

    async def shutdown(self) -> None:
        await self._stack.aclose()
        self.sessions.clear()
        self.tool_to_server.clear()
        self.tools.clear()


# Module-level singleton — import this from app.py.
manager = MCPManager()

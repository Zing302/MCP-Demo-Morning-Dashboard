# Agent layer — the tool-use loop that sits between the routes (app.py) and the
# MCP transport (mcp_client.py). Owns the Anthropic client + model.
#
# Both call sites use run_tool_loop():
#   - POST /api/chat        : a user turn, looped until Claude stops calling tools
#   - /api/refresh log card : the morning_diagnostic prompt, looped to a summary
#
# This is the NON-streaming version. /api/chat can layer streaming on top later;
# the loop/stop decision still happens at end-of-turn (you need the full tool_use
# blocks before you know whether to loop again).
import os

from anthropic import AsyncAnthropic

from client.mcp_client import manager

anthropic_client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 2048
MAX_TURNS = 10  # safety cap on tool-use round-trips


def _anthropic_tools() -> list[dict]:
    """Adapt MCP Tool objects to the Anthropic tools format (inputSchema -> input_schema)."""
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema,
        }
        for t in manager.list_all_tools()
    ]


def _result_to_text(result) -> str:
    """Normalize manager.call_tool() output into the string for a tool_result block.

    Success -> CallToolResult with .content blocks; failure -> {"error": ...} dict.
    """
    if isinstance(result, dict) and "error" in result:
        return f"ERROR: {result['error']}"
    parts = [getattr(b, "text", "") for b in (getattr(result, "content", None) or [])]
    text = "\n".join(p for p in parts if p)
    if getattr(result, "isError", False):
        return f"ERROR: {text or 'tool reported an error'}"
    return text or "(no output)"


def _assistant_text(response) -> str:
    """Concatenate the text blocks of an assistant response."""
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


async def run_tool_loop(messages: list[dict], system: str = "") -> str:
    """Drive Claude through the tool-use loop until it stops requesting tools.

    `messages` is mutated in place (so the caller ends up with the full history).
    Returns the final assistant text.
    """
    tools = _anthropic_tools()
    kwargs = {"model": MODEL, "max_tokens": MAX_TOKENS, "tools": tools}
    if system:
        kwargs["system"] = system

    response = None
    for _ in range(MAX_TURNS):
        response = await anthropic_client.messages.create(messages=messages, **kwargs)
        # Record the assistant turn (text and/or tool_use blocks) verbatim.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return _assistant_text(response)

        # Execute every requested tool call and feed the results back as one user turn.
        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                result = await manager.call_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _result_to_text(result),
                })
        messages.append({"role": "user", "content": tool_results})

    # Hit the safety cap — return whatever text the last turn produced.
    return _assistant_text(response) if response else ""

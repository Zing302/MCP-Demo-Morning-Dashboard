# client/system_prompt.py

from datetime import datetime

def build_system_prompt(available_tools: dict) -> str:
    """Build the dynamic system prompt from the live tool list.

    available_tools: {server_name: [tool_name, ...]} — pass manager.tools_by_server().
    Only connected servers appear, so the prompt reflects graceful degradation.
    """
    today = datetime.now().strftime("%A, %B %d, %Y")

    server_descriptions = {
        "calendar": "Events, todos, and daily schedule",
        "journal": "Diary entries, mood tracking, and weekly summary",
        "weather": "Multi-source weather forecast and synthesis",
        "market_news": "Stock watchlist and AI/tech headlines",
        "log": "Cross-server activity monitoring and habit tracking",
    }

    connected_servers = "\n".join(
        f"- {name}: {server_descriptions[name]} | tools: {', '.join(tools)}"
        for name, tools in available_tools.items()
        if name in server_descriptions
    )

    return f"""Today is {today}.

You are a personal morning assistant with access to the following MCP servers:

{connected_servers}

When responding to the user:
- Decide which servers are relevant to the query and call their tools
- Call multiple servers in a single response when the query spans more than one domain
- Synthesize all tool results into a single conversational, concise answer
- Do not list raw tool outputs — integrate them naturally into your response
- If a server is not listed above, do not attempt to call it
- Match response length to available data — sparse tool results warrant a short reply, not a full briefing
- Do not infer the day of the week or any date-related information beyond what is explicitly stated in today's date: {today}
"""
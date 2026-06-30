# MCP Server: Log
# Run via: python -m servers.log.server
# Transport: stdio
# Passive receiver — reads activity.log written by shared/logger.py
# Every other server calls log_action() — this server never calls them
import os
import json
from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP

# NOTE: this server does NOT import shared.logger — it is the passive *reader* of
# activity.log. Every other server writes; the log server only reads.

mcp = FastMCP("log")

LOG_DATA_PATH = os.getenv("LOG_DATA_PATH", "./data/activity.log")
KNOWN_SERVERS = ["calendar", "journal", "weather", "market_news"]
TIME_RANGES = {"1h": 3600, "24h": 86400, "7d": 604800}

# --- Tools ---

@mcp.tool()
def get_activity_history(range: str = "24h"):
    """Return tool call history. range: '1h' | '24h' | '7d'"""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=TIME_RANGES.get(range, 86400))
    entries = []
    if not os.path.exists(LOG_DATA_PATH):
        return entries
    with open(LOG_DATA_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if datetime.fromisoformat(entry["timestamp"]) >= cutoff:
                entries.append(entry)
    return entries

# Maps raw internal tool names to friendly, user-facing activity phrases.
# Users must NEVER see raw tool or server names. Unknown tools are skipped.
TOOL_PHRASES = {
    "get_events_today": "checked your schedule",
    "compile_daily_schedule": "checked your schedule",
    "get_todo_list": "checked your schedule",
    "get_todo_history": "checked your schedule",
    "add_event": "added a calendar event",
    "add_todo": "added a to-do",
    "complete_todo": "completed a to-do",
    "remove_event": "updated your calendar",
    "update_event": "updated your calendar",
    "get_price": "checked the markets",
    "get_portfolio_summary": "checked the markets",
    "get_movers": "checked the markets",
    "get_headlines": "read the news",
    "search_web": "read the news",
    "write_entry": "wrote in your journal",
    "get_weekly_summary": "reviewed your journal",
    "list_entries": "reviewed your journal",
    "get_forecast_openweather": "checked the weather",
    "get_forecast_wttr": "checked the weather",
    "synthesize_forecast": "checked the weather",
}


def _format_hour(hour: int) -> str:
    """Format a 0-23 hour as a 12-hour am/pm label, e.g. '8am', '12pm', '3pm'."""
    suffix = "am" if hour < 12 else "pm"
    display = hour % 12
    if display == 0:
        display = 12
    return f"{display}{suffix}"


@mcp.tool()
def get_habit_summary():
    """Summarize activity patterns: one concise line per activity (not per hour),
    showing total count and the time of day it most often happens. Top 6 by frequency."""
    log_data = get_activity_history("7d")
    # phrase -> {"total": count, "hours": {hour: count}}
    stats = {}
    for entry in log_data:
        phrase = TOOL_PHRASES.get(entry["tool"])
        if phrase is None:
            continue  # skip unknown tools — never expose raw names
        # Timestamps are UTC; convert to local so the displayed time matches the clock.
        hour = datetime.fromisoformat(entry["timestamp"]).astimezone().hour
        s = stats.setdefault(phrase, {"total": 0, "hours": {}})
        s["total"] += 1
        s["hours"][hour] = s["hours"].get(hour, 0) + 1

    summary = []
    for phrase, s in sorted(stats.items(), key=lambda kv: kv[1]["total"], reverse=True)[:6]:
        peak_hour = max(s["hours"].items(), key=lambda kv: kv[1])[0]
        times = "once" if s["total"] == 1 else f"{s['total']} times"
        summary.append(f"You {phrase}, usually around {_format_hour(peak_hour)} ({times} this week).")
    return "\n".join(summary)

@mcp.tool()
def diagnose_server(server_name: str = "all"):
    """Check recent log entries per server and return health status.
    Returns { server: "healthy" | "degraded" | "no recent activity" }."""
    servers = KNOWN_SERVERS if server_name == "all" else [server_name]
    log_data = get_activity_history("24h")
    result = {}
    for s in servers:
        recent = [e for e in log_data if e["server"] == s]
        if not recent:
            result[s] = "no recent activity"
        elif len(recent) < 5:
            result[s] = "degraded"
        else:
            result[s] = "healthy"
    return result

@mcp.tool()
def get_last_action():
    """Return the most recent log entry across all servers."""
    if not os.path.exists(LOG_DATA_PATH):
        return None
    with open(LOG_DATA_PATH, "r") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    if lines:
        return json.loads(lines[-1])
    return None

# --- Prompts ---

@mcp.prompt()
def morning_diagnostic():
    """
    Powers the Log dashboard card on refresh. Not user triggered.
    A prompt does NOT call tools itself — it returns a templated message that
    instructs Claude to call get_activity_history, get_habit_summary,
    diagnose_server, and get_last_action, then synthesize a health + habit summary.
    The client feeds this prompt to Claude with the toolset and runs the tool-use
    loop (Claude calls the tools, the client returns results, Claude synthesizes —
    multiple round-trips) to populate the card.
    Instruct Claude: structured output only, ask the user nothing.
    """
    # TODO: return prompt string that sequences all 4 tools above
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = [
        {
            "role": "user",
            "content": f"""
Today is {today}.

You are running an automated morning diagnostic for the dashboard Log card.
Do not greet the user. Do not ask questions. Return structured output only.

Call the following tools in order:
1. get_activity_history(range="24h")
2. get_habit_summary()
3. diagnose_server(server_name="all")
4. get_last_action()

Then synthesize the results into this exact structure:

SYSTEM HEALTH
-------------
<one line per component (servers, databases, cache layers, etc.): name — healthy / degraded / critical / no recent activity>

HABIT SUMMARY
-------------
<exactly 2-3 sentences. Report ONLY what is explicitly stated in the tool results — do not infer, interpret, or add information not present in the data. Do not correct or modify malformed timestamps — reproduce them exactly as returned.>

LAST ACTION
-----------
<one line per recent action: server | tool | timestamp | status>
"""
        }
    ]
    return prompt

if __name__ == "__main__":
    mcp.run()

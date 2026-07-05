# MCP Server: Journal
# Run via: python -m servers.journal.server
# Transport: stdio
# Demonstrates all 3 MCP primitives: tools, resources, prompts
import json
import os
import uuid
from datetime import date, datetime
from mcp.server.fastmcp import FastMCP
from shared.logger import log_action

mcp = FastMCP("journal")

# --- Local JSON store helpers (not MCP tools) ---

def load() -> dict:
    """Reads the journal store. Returns {"entries": [...]}."""
    JOURNAL_PATH = os.getenv("JOURNAL_DATA_PATH", "./data/journal.json")
    if not os.path.exists(JOURNAL_PATH):
        return {"entries": []}
    with open(JOURNAL_PATH) as f:
        data = json.load(f)
    data.setdefault("entries", [])
    return data

def save(data: dict) -> None:
    """Write the journal store back to disk."""
    JOURNAL_PATH = os.getenv("JOURNAL_DATA_PATH", "./data/journal.json")
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    with open(JOURNAL_PATH, "w") as f:
        json.dump(data, f, indent=2)

# --- Tools ---

@mcp.tool()
def write_entry(date: str, content: str, mood: str):
    """Write a journal entry. mood: 'good' | 'neutral' | 'tough'"""
    # TODO: append to journal JSON store
    new_entry = {
        "id": str(uuid.uuid4()),
        "date": date,
        "content": content,
        "mood": mood,
        "created_at": datetime.now().date().isoformat(),
    }
    data = load()
    data["entries"].append(new_entry)
    save(data)
    log_action("journal", "write_entry")
    return {"status": "success", "entry_id": new_entry["id"]}

@mcp.tool()
def list_entries(days: int = 7):
    """Return the last N days of journal entries."""
    # TODO: filter journal store by date range, return list[JournalEntry]
    today = date.today()
    entries_in_range = [
        entry for entry in load()["entries"]
        if (0 <= (today - date.fromisoformat(entry.get("date"))).days < days)
    ]
    log_action("journal", "list_entries")
    return entries_in_range

@mcp.tool()
def get_weekly_summary():
    """Return a structured summary of the last 7 journal entries.
    Drives the Journal dashboard card on refresh — a direct tool call, no LLM."""
    # TODO: aggregate entries, return summary string for dashboard card
    last_7_entries = list_entries(days=7)
    summary = {
        "total_entries": len(last_7_entries),
        "mood_counts": {
            "good": sum(1 for e in last_7_entries if e.get("mood") == "good"),
            "neutral": sum(1 for e in last_7_entries if e.get("mood") == "neutral"),
            "tough": sum(1 for e in last_7_entries if e.get("mood") == "tough"),
        },
    }
    log_action("journal", "get_weekly_summary")
    return summary

# --- Resources ---

@mcp.resource("journal://entries/{date}")
def get_entry_by_date(date: str):
    """Read-only access to a single journal entry by date."""
    # TODO: look up entry in journal store by date, return JournalEntry
    for entry in load()["entries"]:
        if entry.get("date") == date:
            log_action("journal", "get_entry_by_date")
            return entry

@mcp.resource("journal://entries/recent")
def get_recent_entries():
    """Read-only access to the last 7 days of entries."""
    # TODO: return last 7 entries from journal store
    recent_entries = list_entries(days=7)
    log_action("journal", "get_recent_entries")
    return recent_entries

# --- Prompts ---

@mcp.prompt()
def open_journal():
    """
    User-invoked from the chat panel ("journal with me") — NOT used for the card.
    Opens an interactive journaling session: sets a calm reflective tone,
    injects today's date, references journal://entries/recent for context.
    Claude begins by asking how the user's day is going.
    """
    # TODO: return prompt string with {date} injected and resource reference
    today = date.today().isoformat()
    prompt = [
            {
                "role": "user",
                "content": f"""
You are a calm, reflective journaling companion.

Today is {today}.

Before responding, read the user's recent journal entries available at:
journal://entries/recent

Use them only for quiet context — do not reference or summarize them unless 
the user brings them up. Speak warmly and simply. No bullet points, 
no structure, no advice unless asked.

Begin by asking how their day is going. One sentence only.
                """
            }
        ]
    log_action("journal", "open_journal")
    return prompt


if __name__ == "__main__":
    mcp.run()

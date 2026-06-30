# MCP Server: Calendar
# Run via: python -m servers.calendar.server
# Transport: stdio
import json
import os
import uuid
from datetime import date
from mcp.server.fastmcp import FastMCP
from shared.logger import log_action

mcp = FastMCP("calendar")

CALENDAR_PATH = os.getenv("CALENDAR_DATA_PATH", "./data/calendar.json")


# --- Local JSON store helpers (not MCP tools) ---

def load() -> dict:
    """Read the calendar store. Returns {"events": [...], "todos": [...]}."""
    if not os.path.exists(CALENDAR_PATH):
        return {"events": [], "todos": []}
    with open(CALENDAR_PATH) as f:
        data = json.load(f)
    data.setdefault("events", [])
    data.setdefault("todos", [])
    return data


def save(data: dict) -> None:
    """Write the calendar store back to disk."""
    os.makedirs(os.path.dirname(CALENDAR_PATH), exist_ok=True)
    with open(CALENDAR_PATH, "w") as f:
        json.dump(data, f, indent=2)


# --- Tools ---

@mcp.tool()
def connect_calendar():
    """Confirm the local JSON store (CALENDAR_DATA_PATH) is reachable."""
    data = load()
    log_action("calendar", "connect_calendar")
    return {
        "status": "connected",
        "path": CALENDAR_PATH,
        "events": len(data["events"]),
        "todos": len(data["todos"]),
    }


@mcp.tool()
def get_events_today():
    """Return today's events from the calendar store."""
    today = date.today().isoformat()
    todays_events = [e for e in load()["events"] if e.get("date") == today]
    log_action("calendar", "get_events_today")
    return todays_events


@mcp.tool()
def compile_daily_schedule():
    """Pull today's events + pending todos into a structured summary."""
    daily_schedule = {
        "events": get_events_today(),
        "todos": get_todo_list(),
    }
    log_action("calendar", "compile_daily_schedule")
    return daily_schedule


@mcp.tool()
def add_event(title: str, time: str, duration_minutes: int, event_date: str = None):
    """Add a new event to the calendar store. event_date is ISO 'YYYY-MM-DD' (defaults to today)."""
    new_event = {
        "id": str(uuid.uuid4()),
        "title": title,
        "date": event_date or date.today().isoformat(),
        "time": time,
        "duration_minutes": duration_minutes,
    }
    data = load()
    data["events"].append(new_event)
    save(data)
    log_action("calendar", "add_event")
    return new_event


@mcp.tool()
def remove_event(event_id: str):
    """Remove an event from the calendar store by ID."""
    data = load()
    remaining = [e for e in data["events"] if e["id"] != event_id]
    if len(remaining) == len(data["events"]):
        log_action("calendar", "remove_event", status="error")
        return {"status": "error", "message": f"Event {event_id} not found."}
    data["events"] = remaining
    save(data)
    log_action("calendar", "remove_event")
    return {"status": "success", "message": f"Event {event_id} removed."}


@mcp.tool()
def update_event(event_id: str, title: str = None, time: str = None,
                 duration_minutes: int = None, event_date: str = None):
    """Update an existing event in the calendar store."""
    data = load()
    for event in data["events"]:
        if event["id"] == event_id:
            if title is not None:
                event["title"] = title
            if time is not None:
                event["time"] = time
            if duration_minutes is not None:
                event["duration_minutes"] = duration_minutes
            if event_date is not None:
                event["date"] = event_date
            save(data)
            log_action("calendar", "update_event")
            return event
    log_action("calendar", "update_event", status="error")
    return {"status": "error", "message": f"Event {event_id} not found."}


@mcp.tool()
def get_todo_list():
    """Return the current list of pending (not done) todos, regardless of due date."""
    pending_todos = [t for t in load().get("todos", []) if not t.get("done", False)]
    log_action("calendar", "get_todo_list")
    return pending_todos


@mcp.tool()
def get_todo_history(days: int = 7):
    """Return completed and pending todos from the last N days."""
    # TODO: filter todo store by date range, return list[TodoItem]
    todo_in_range = []
    calendar_data = load()
    for todo in calendar_data.get("todos", []):
        todo_date = todo.get("due")
        if todo_date:
            todo_date_obj = date.fromisoformat(todo_date)
            # Only past-through-today within the window — exclude future-dated todos.
            if 0 <= (date.today() - todo_date_obj).days <= days:
                todo_in_range.append(todo)
    log_action("calendar", "get_todo_history")
    return todo_in_range


@mcp.tool()
def add_todo(title: str, due: str = None):
    """Add a new todo. due is ISO 'YYYY-MM-DD' (optional)."""
    new_todo = {
        "id": str(uuid.uuid4()),
        "title": title,
        "due": due,
        "done": False,
    }
    data = load()
    data["todos"].append(new_todo)
    save(data)
    log_action("calendar", "add_todo")
    return new_todo


@mcp.tool()
def complete_todo(todo_id: str):
    """Mark a todo as done by ID."""
    data = load()
    for todo in data["todos"]:
        if todo["id"] == todo_id:
            todo["done"] = True
            save(data)
            log_action("calendar", "complete_todo")
            return todo
    log_action("calendar", "complete_todo", status="error")
    return {"status": "error", "message": f"Todo {todo_id} not found."}


if __name__ == "__main__":
    mcp.run()

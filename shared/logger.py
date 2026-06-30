"""
Shared logger utility — every MCP server imports this to log tool calls.
Log server reads the same file. This is the passive coupling mechanism.
"""
import json
import os
from datetime import datetime, timezone
from shared.models import LogEntry

LOG_PATH = os.getenv("LOG_DATA_PATH", "./data/activity.log")

def log_action(server: str, tool: str, status: str = "success",
               duration_ms: int = None, error: str = None):
    """Called by every tool in every server as its last line."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    entry = LogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        server=server,
        tool=tool,
        status=status,
        duration_ms=duration_ms,
        error=error
    )
    with open(LOG_PATH, "a") as f:
        f.write(entry.model_dump_json() + "\n")

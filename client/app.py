# FastAPI app — entry point for the dashboard.
#
# Routes:
#   GET  /             -> serve the dashboard
#   GET  /api/refresh  -> populate the 5 cards (hybrid: structured tools + log prompt)
#   POST /api/chat     -> chat through the tool-use loop
#   GET  /api/status   -> per-server connection status (green/red dots)
#
# load_dotenv() runs FIRST (below) so the env vars exist before we import the agent
# (which builds the Anthropic client) and before manager.startup() spawns the
# servers — the child processes inherit those vars.
from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import AnyUrl, BaseModel

from client.mcp_client import manager
from client.agent import run_tool_loop
from client.system_prompt import build_system_prompt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup/shutdown share the manager's AsyncExitStack — must be the same task,
    # which the FastAPI lifespan guarantees.
    await manager.startup()
    try:
        yield
    finally:
        await manager.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# --- helpers -----------------------------------------------------------------

async def _card(tool: str, args: dict | None = None):
    """Call one tool and normalize its output.

    FastMCP returns a tool's list as one content block PER element, so we parse
    every block: multiple blocks -> a list; a single block -> that value (dict/str).
    """
    result = await manager.call_tool(tool, args or {})
    if isinstance(result, dict) and "error" in result:
        return result
    parsed = []
    for block in (getattr(result, "content", None) or []):
        text = getattr(block, "text", "")
        try:
            parsed.append(json.loads(text))
        except (ValueError, TypeError):
            parsed.append(text)
    if not parsed:
        return None
    return parsed[0] if len(parsed) == 1 else parsed


async def _log_card():
    """Log card: feed the morning_diagnostic prompt through the tool-use loop."""
    session = manager.sessions.get("log")
    if session is None:
        return {"error": "log server not connected"}
    prompt = await session.get_prompt("morning_diagnostic")
    messages = [{"role": m.role, "content": m.content.text} for m in prompt.messages]
    return await run_tool_loop(messages)


# MCP RESOURCE primitive: the journal card reads read-only data by URI. The host
# pulls it directly (application-controlled) — no LLM decides anything — and does
# the mood aggregation itself. Contrast with tools (model-controlled).
JOURNAL_RECENT_URI = "journal://entries/recent"


async def _journal_card():
    """Journal card, sourced from the `journal://entries/recent` RESOURCE.

    Reads the raw last-7-days entries via the resource, then aggregates the mood
    counts host-side into the shape renderJournal() expects.
    """
    session = manager.sessions.get("journal")
    if session is None:
        return {"error": "journal server not connected"}
    result = await session.read_resource(AnyUrl(JOURNAL_RECENT_URI))
    entries = []
    for block in result.contents:
        text = getattr(block, "text", "")
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        entries.extend(data if isinstance(data, list) else [data])
    counts = {"good": 0, "neutral": 0, "tough": 0}
    for e in entries:
        if isinstance(e, dict) and e.get("mood") in counts:
            counts[e["mood"]] += 1
    return {"total_entries": len(entries), "mood_counts": counts}


# MCP PROMPT primitive: a user action ("open journal" in chat) invokes a named
# server-side template, whose messages seed the conversation.
JOURNAL_PROMPT_TRIGGERS = {"open journal", "journal with me", "/open_journal"}


def _reply_text(result) -> str:
    """run_tool_loop returns a string; a helper may return an {"error": ...} dict."""
    if isinstance(result, dict) and "error" in result:
        return f"Sorry — {result['error']}."
    return result if isinstance(result, str) else str(result)


async def _open_journal_prompt():
    """Fetch the journal server's `open_journal` prompt and run it. The template's
    own persona drives the turn, so we intentionally pass no system prompt."""
    session = manager.sessions.get("journal")
    if session is None:
        return {"error": "journal server not connected"}
    prompt = await session.get_prompt("open_journal")
    messages = [{"role": m.role, "content": m.content.text} for m in prompt.messages]
    return await run_tool_loop(messages)


# --- routes ------------------------------------------------------------------

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


async def _safe(coro):
    try:
        return await coro
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/refresh")
async def refresh():
    """The fast cards, gathered in PARALLEL (so total time ~= the slowest, not the sum).
    The two slow cards load via their own endpoints so they never block the grid:
      - stocks  -> /api/card/stocks  (yfinance, ~3.5s)
      - log     -> /api/card/log     (LLM tool-loop)
    """
    calendar, journal, weather, headlines, habits = await asyncio.gather(
        _safe(_card("compile_daily_schedule")),
        _safe(_journal_card()),
        _safe(_card("synthesize_forecast", {"location": ""})),
        _safe(_card("get_headlines", {"topic": "AI technology", "limit": 5})),
        _safe(_card("get_habit_summary")),
    )
    return {
        "calendar": calendar,
        "journal": journal,
        "weather": weather,
        "market_news": {"headlines": headlines},  # stocks fetched separately
        "habits": habits,
    }


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": str}, ...]


@app.post("/api/chat")
async def chat(req: ChatRequest):
    # A user action can invoke a named MCP prompt template instead of a free chat turn.
    if req.message.strip().lower() in JOURNAL_PROMPT_TRIGGERS:
        return {"reply": _reply_text(await _open_journal_prompt())}
    system = build_system_prompt(manager.tools_by_server())
    messages = req.history + [{"role": "user", "content": req.message}]
    reply = await run_tool_loop(messages, system=system)
    return {"reply": reply}


class EventRequest(BaseModel):
    title: str
    time: str
    duration_minutes: int = 30
    event_date: str | None = None


class TodoRequest(BaseModel):
    title: str
    due: str | None = None


@app.post("/api/calendar/event")
async def add_event(req: EventRequest):
    return await _card("add_event", req.model_dump(exclude_none=True))


@app.post("/api/calendar/todo")
async def add_todo(req: TodoRequest):
    return await _card("add_todo", req.model_dump(exclude_none=True))


class CalendarIdRequest(BaseModel):
    id: str


@app.post("/api/calendar/todo/complete")
async def complete_todo(req: CalendarIdRequest):
    return await _card("complete_todo", {"todo_id": req.id})


@app.post("/api/calendar/event/remove")
async def remove_event(req: CalendarIdRequest):
    return await _card("remove_event", {"event_id": req.id})


@app.get("/api/card/stocks")
async def card_stocks():
    """Watchlist — fetched separately because yfinance is slow (~3.5s)."""
    return await _safe(_card("get_portfolio_summary"))


@app.get("/api/card/log")
async def card_log():
    """The System Health card — fetched separately because it runs an LLM tool-loop
    and must not block the fast cards in /api/refresh."""
    try:
        return await _log_card()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/card/calendar")
async def card_calendar():
    """Lightweight single-card refresh so calendar edits don't re-run the whole
    /api/refresh (which includes the LLM-backed log card)."""
    try:
        return await _card("compile_daily_schedule")
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/status")
async def status():
    return manager.status()

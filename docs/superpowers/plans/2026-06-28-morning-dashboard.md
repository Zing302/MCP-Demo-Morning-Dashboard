# Morning Dashboard (MCP Demo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily morning dashboard powered by 5 independent stdio MCP servers and a FastAPI client, as a teaching demo for the core MCP primitives (tools, resources, prompts).

**Architecture:** Five stdio MCP servers (calendar, journal, weather, market_news, log) each run as `python -m servers.<name>.server`. A FastAPI client spawns all five as subprocesses, discovers their tools, builds a dynamic system prompt, and serves a dashboard with 5 data cards + a chat panel. Servers are decoupled — they communicate only through a shared append-only `activity.log` that every tool writes to and the `log` server reads (passive coupling).

**Tech Stack:** Python, `mcp` SDK (`mcp.server.fastmcp.FastMCP`), FastAPI + uvicorn + Jinja2, Anthropic SDK, yfinance (stocks), feedparser + Google News RSS (news), OpenWeatherMap + wttr.in (weather), Pydantic.

## Global Constraints

- MCP entrypoint is `from mcp.server.fastmcp import FastMCP` (NOT `from mcp import FastMCP`).
- News uses Google News RSS via `feedparser` — no API key. Only Anthropic + OpenWeather keys are required.
- Every server tool calls `log_action(server, tool, ...)` from `shared/logger.py` as its final step — EXCEPT the `log` server, which is the passive reader and never writes.
- Servers must be spawned with `command = sys.executable` (NOT the bare `"python"` in `mcp_config.json`, which may resolve to an interpreter without `mcp`), cwd / `PYTHONPATH` = repo root, and `env = os.environ` so imports and per-server env vars resolve.
- `load_dotenv()` runs once in `client/app.py` at import, BEFORE `mcp_client.startup()`, so spawned children inherit the env vars they read.
- This project intentionally has no test suite (it is a tutorial); each task ends with a runnable smoke-check instead.
- Not a git repository — commits are out of scope unless the user runs `git init`.

## Locked Review Decisions

1. **FastMCP import path** — corrected across all 5 servers. *(done)*
2. **News source** — Google News RSS + `feedparser` instead of Brave Search API; dropped `beautifulsoup4` and `BRAVE_SEARCH_API_KEY`. `search_web` is a *news* search, not general web. *(done)*
3. **`/api/refresh` card mechanism (hybrid):** structured cards (calendar, weather, market_news, journal) populate via **direct tool calls** (no LLM); the **log** card populates via the `morning_diagnostic` **prompt** run through the tool-use loop (Claude calls the 4 log tools, then synthesizes — *multiple* round-trips, not one). The `open_journal` prompt is the chat panel's "journal with me" entry point, not a card source. *(documented in stubs)*
4. **Prompt semantics** — a prompt returns a templated instruction; it does not execute tools itself. Docstrings corrected. *(done)*
5. **Subprocess working directory** — documented in `mcp_client.startup()`. *(done)*

---

## Build Order

Each task fills in the TODO stubs for one unit and ends with a smoke-check.

### Task 1: `shared/models.py` + `shared/logger.py`
- [ ] Confirm Pydantic models cover all server return shapes; `log_action` writes one JSON line per call to `LOG_DATA_PATH`.
- [ ] Smoke: `python -c "from shared.logger import log_action; log_action('test','t')"` then verify a line appears in `data/activity.log`.

### Task 2: `servers/log/server.py` *(done)*
- [x] `get_activity_history`, `get_habit_summary`, `diagnose_server`, `get_last_action` — ISO-timestamp aware, single-read, missing-file guarded, real server names, no stdout writes; `LOG_DATA_PATH` default matches the writer.
- [x] `morning_diagnostic` prompt renders through FastMCP to a valid `GetPromptResult` (returns a bare message list, date injected, sequences the 4 tools).
- [x] Smoke: all tools verified against a seeded multi-server log; prompt render verified.

### Task 3: `servers/calendar/server.py` *(done)*
- [x] `load()/save()` JSON helpers over `CALENDAR_DATA_PATH`; `CalendarEvent` gained a `date` field.
- [x] Events: `connect_calendar`, `get_events_today`, `compile_daily_schedule`, `add_event`, `remove_event`, `update_event`.
- [x] Todos: `get_todo_list` (pending), `get_todo_history` (past-through-today window), `add_todo`, `complete_todo`.
- [x] Smoke: full event + todo CRUD verified, including dueless/future/old todo edge cases.

### Task 4: `servers/journal/server.py` *(done)*
- [x] `load()/save()` JSON helpers over `JOURNAL_DATA_PATH`; `JournalEntry` carries `id` + `created_at`; mood vocab is `good|neutral|tough`.
- [x] Tools (`write_entry`, `list_entries` [today-inclusive window], `get_weekly_summary` with mood counts), resources (`journal://entries/{date}`, `.../recent`), and the `open_journal` prompt (returns a user message, date injected, references the recent resource).
- [x] Smoke: prompt renders through FastMCP to a valid `GetPromptResult`; entries round-trip via tools + resources.

### Task 5: `servers/weather/server.py` *(done)*
- [x] `get_forecast_openweather` (real OWM call, `units=imperial`) and `get_forecast_wttr` both return structured `WeatherData`.
- [x] `synthesize_forecast` reconciles the two (averages temp/humidity, keeps both raw sources) and degrades gracefully if one source fails (e.g. no OWM key → wttr-only).
- [x] Location resolves as arg → `WEATHER_LOCATION` → default; handles the empty-env default.
- [x] Smoke: synthesis, single-source degradation, and no-source error paths all verified.

### Task 6: `servers/market_news/server.py` *(done)*
- [x] Stocks: `get_price` (computes `change_pct` from `last_price`/`previous_close`, returns `{ticker, price, change_pct}`, errors via `log_action`), `get_portfolio_summary` (skips invalid tickers, strips whitespace), `get_movers`.
- [x] News: `get_headlines` and `search_web` (capped at 25, `entry.get(...)` for safety, `source` flattened to its title string).
- [x] Smoke: stocks pipeline verified (mocked yfinance); news verified live against Google News RSS.

### Task 7: `client/mcp_client.py` *(done)*
- [x] `MCPManager` holds all sessions in an `AsyncExitStack`: `startup` spawns 5 servers (`sys.executable`, repo-root cwd, `PYTHONPATH`+env), `initialize()`s, and indexes tools into `tool_to_server`.
- [x] `list_all_tools`, `call_tool(tool, args)` (routes via the map, graceful error dict), `status()` (per-server connected/down), `shutdown()`. Module-level `manager` singleton.
- [x] Smoke: live integration — all 5 connect, 25 tools discovered, `call_tool` routed, unknown-tool + shutdown paths verified. Must be driven from FastAPI lifespan (same-task exit stack).

### Task 8: `client/system_prompt.py` *(done)*
- [x] `build_system_prompt({server: [tool_names]})` — date, per-server responsibilities, injected live tool list, response guidance. Contract documented; pass `manager.tools_by_server()`.
- [x] `MCPManager.tools_by_server()` added (Task 7) to adapt the flat tool list into the prompt's shape.
- [x] Smoke: live — 25 tools across 5 servers render; only connected servers appear (graceful degradation).

### Task 9: Tool-use loop — `client/agent.py` *(built; live LLM run pending)*
- [x] New `client/agent.py` owns the Anthropic client + model (`claude-sonnet-4-6`, env-overridable), keeping LLM concerns out of `mcp_client.py`.
- [x] `_anthropic_tools()` adapts MCP `Tool`s (`inputSchema` -> `input_schema`); `_result_to_text()` normalizes success `CallToolResult` vs `{"error": ...}` into `tool_result` content.
- [x] `run_tool_loop(messages, system="")`: call Claude → execute `tool_use` blocks via `manager.call_tool` → feed `tool_result`s → repeat until `stop_reason != "tool_use"` (capped at `MAX_TURNS`). Mutates `messages`, returns final text.
- [x] Deterministic smoke: 25 tools adapt correctly; normalizer verified both paths.
- [x] Live smoke: "what events/todos today?" chat triggered the calendar tools then a synthesized answer; multi-turn history recalled; the log card synthesized a SYSTEM HEALTH summary after the log tools.

### Task 10: `client/app.py` + templates + static *(done)*
- [x] `load_dotenv()` first; FastAPI lifespan drives `manager.startup()/shutdown()`; static + Jinja2 mounted.
- [x] `GET /api/refresh` (4 structured cards via `_card`, log card via `_log_card` + `run_tool_loop`, each guarded), `POST /api/chat` (system prompt + history + `run_tool_loop`), `GET /api/status`.
- [x] Frontend (adapted from Stitch mockups into one page): `index.html` + `dashboard.css` + `dashboard.js` — 6 cards (weather, system-health log, calendar flow, weekly mood, watchlist, headlines), header status dots, refresh button, floating chat. Per-card loading skeletons + error/empty states; chat keeps its own history.
- [x] Live smoke via TestClient: servers connect; `/` + static assets serve 200; refresh returns all cards (calendar parsed, log synthesized); chat triggers tools + handles history.
- [ ] Manual visual pass: `uvicorn client.app:app --reload` → http://localhost:8000 (needs a browser).

## Self-Review Notes
- Spec coverage: every README section maps to a task above.
- The 5 review decisions are reflected in the current stubs; no contradictions remain (grep confirms no Brave/bs4/`from mcp import FastMCP`).
- Open dependency to install before Task 6: `feedparser` (already added to `requirements.txt`).

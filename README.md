# Morning Dashboard — MCP Demo

A daily morning dashboard powered by **5 independent MCP servers** and a FastAPI client.
Built to demonstrate the full Model Context Protocol surface: tools, resources, prompts,
multi-server stdio orchestration, a dynamic system prompt, and the agent tool-use loop.

## What it does

A single-page dashboard with seven live cards plus an AI chat assistant:

| Card | Source | Notes |
|---|---|---|
| **Weather** | OpenWeatherMap + wttr.in | temp, condition, feels-like, humidity, wind, high/low — two sources reconciled |
| **Today's Flow** | Calendar (local JSON) | today's events + interactive to-dos: check to complete, × to remove, add events/to-dos for any date |
| **Weekly Mood** | Journal (local JSON) | entry count + good/neutral/tough breakdown |
| **Habits** | Log server | summarized activity patterns inferred from the cross-server activity log |
| **Watchlist** | yfinance | watchlist prices + daily % change |
| **Headlines** | Google News RSS | latest stories for a topic |
| **System Health** | Log server + Claude | an LLM-synthesized health + habit report, driven by an MCP prompt through the tool-use loop |
| **Chat** | Claude + all servers | ask anything; Claude calls the right tools and synthesizes an answer |

## Architecture

```
client/
  app.py              # FastAPI — lifespan spawns servers; /api/refresh (fast cards),
                      #           /api/card/{stocks,log,calendar}, /api/chat, /api/status,
                      #           /api/calendar/{event,todo,event/remove,todo/complete}
  mcp_client.py       # MCPManager — spawns all 5 servers (sys.executable + repo-root cwd),
                      #              ClientSession per server, tool routing, graceful degradation
  agent.py            # Anthropic client + run_tool_loop() — the tool-use loop, shared by
                      #              the chat endpoint and the System Health card
  system_prompt.py    # Builds the dynamic system prompt from the live tool list
  templates/index.html
  static/css/dashboard.css
  static/js/dashboard.js   # Per-card async loading, calendar interactions, chat rendering

servers/
  calendar/server.py  # @mcp.tool: connect_calendar, get_events_today, compile_daily_schedule,
                      #            add_event, remove_event, update_event,
                      #            get_todo_list, get_todo_history, add_todo, complete_todo
  journal/server.py   # @mcp.tool:     write_entry, list_entries, get_weekly_summary
                      # @mcp.resource: journal://entries/{date}, journal://entries/recent
                      # @mcp.prompt:   open_journal
  weather/server.py   # @mcp.tool: get_forecast_openweather, get_forecast_wttr, synthesize_forecast
  market_news/server.py  # @mcp.tool: get_price, get_portfolio_summary, get_movers,
                         #            get_headlines, search_web
  log/server.py       # @mcp.tool:   get_activity_history, get_habit_summary,
                      #              diagnose_server, get_last_action
                      # @mcp.prompt: morning_diagnostic

shared/
  logger.py           # log_action() — imported by every server except log; passive logging
  models.py           # Pydantic models shared across servers

data/                 # Local stores (calendar.json, journal.json, activity.log)
mcp_config.json       # Server definitions
.env.example          # All required env vars
requirements.txt
```

## MCP concepts demonstrated

| Concept | Where |
|---|---|
| `@mcp.tool()` — schema, registration, calling | every server |
| `@mcp.resource()` — read-only data | journal/server.py |
| `@mcp.prompt()` — templated messages (not tool executors) | journal/server.py, log/server.py |
| stdio transport | mcp_config.json + mcp_client.py |
| Multi-server orchestration | client/mcp_client.py |
| Dynamic system prompt | client/system_prompt.py |
| Agent tool-use loop | client/agent.py — run_tool_loop() |
| Tool calling another tool | weather/server.py — synthesize_forecast |
| Passive cross-server coupling | shared/logger.py → log/server.py |
| Graceful degradation | mcp_client.call_tool(), per-card error states |

## Quick start

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY (required) and OPENWEATHER_API_KEY (optional)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn client.app:app --reload
# open http://localhost:8000
```

> **Important:** the interpreter that runs `uvicorn` must have all of `requirements.txt`
> installed. `mcp_client` spawns each server with `sys.executable`, so the servers run
> under the *same* interpreter — use a dedicated venv (above) rather than a base/shared
> environment that may be missing `mcp`, `anthropic`, `yfinance`, etc.

Only two keys are needed: **Anthropic** (chat + System Health) and **OpenWeather**
(optional — weather falls back to keyless wttr.in). Stocks, news, calendar, and journal
need no keys.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/refresh` | the fast cards (calendar, journal, weather, headlines, habits), gathered in parallel |
| `GET /api/card/stocks` | watchlist (slow — yfinance, loaded separately) |
| `GET /api/card/log` | System Health (slow — LLM tool-loop, loaded separately) |
| `GET /api/card/calendar` | calendar-only refresh (used after edits, avoids a full reload) |
| `POST /api/chat` | `{message, history}` → `{reply}` via the tool-use loop |
| `POST /api/calendar/event` `/todo` `/event/remove` `/todo/complete` | calendar mutations |
| `GET /api/status` | per-server connection status |

The slow cards (stocks, System Health) load independently so they never block the grid.

## Demo flow

1. Open the dashboard — the fast cards pop in immediately; stocks and System Health fill in after.
2. Point out the **Weather** detail (location, feels-like, wind, high/low).
3. **Check off a to-do** — completes instantly with no full-page reload.
4. **Add an event** (try a future date) — shows the calendar write tools.
5. Open the **chat** and ask "what's on my calendar today?" — Claude calls the calendar tools and synthesizes an answer (the tool-use loop in action).
6. Scroll to **System Health** — an LLM summarizing the log server's cross-server activity data.

Tip: `data/activity.log` accumulates every tool call, so Habits and System Health grow as
you click. Delete it (`rm -f data/activity.log`) for a clean slate before a fresh demo.

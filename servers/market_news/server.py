# MCP Server: Market & News
# Run via: python -m servers.market_news.server
# Transport: stdio
# Two logical groups (stocks + news) in one server — same scaffolding pattern
import os
from urllib.parse import quote
import yfinance as yf
import feedparser
from mcp.server.fastmcp import FastMCP
from shared.logger import log_action

mcp = FastMCP("market_news")

# --- Stocks (yfinance — no API key needed) ---

@mcp.tool()
def get_price(symbol: str):
    """Fetch current price and % change for a single ticker. Returns StockData-shaped dict or None."""
    try:
        info = yf.Ticker(symbol).fast_info
        price = info.last_price
        prev = info.previous_close
        if not price or price <= 0:
            log_action("market_news", "get_price", status="error",
                       error=f"{symbol}: invalid price ({price})")
            return None
        change_pct = (price - prev) / prev * 100 if prev else 0.0
        log_action("market_news", "get_price")
        return {"ticker": symbol, "price": float(price), "change_pct": round(change_pct, 2)}
    except Exception as e:
        log_action("market_news", "get_price", status="error", error=f"{symbol}: {e}")
        return None

@mcp.tool()
def get_portfolio_summary():
    """Fetch current price + % change for full watchlist (STOCK_WATCHLIST env var)."""
    stock_watchlist = os.getenv("STOCK_WATCHLIST", "AAPL,MSFT,NVDA,GOOG").split(",")
    summary = []
    for ticker in stock_watchlist:
        result = get_price(ticker.strip())
        if result is not None:
            summary.append(result)
    log_action("market_news", "get_portfolio_summary")
    return summary

@mcp.tool()
def get_movers():
    """Return the top gainer and top loser from the watchlist today."""
    summary = get_portfolio_summary()
    if not summary:
        return {"top_gainer": None, "top_loser": None}
    sorted_summary = sorted(summary, key=lambda x: x["change_pct"], reverse=True)
    top_gainer = sorted_summary[0]
    top_loser = sorted_summary[-1]
    log_action("market_news", "get_movers")
    return {"top_gainer": top_gainer, "top_loser": top_loser}

# --- News (Google News RSS via feedparser — no API key needed) ---
# Same pattern as stocks above: a free, keyless data source through a library.

NEWS_RSS_SEARCH = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

@mcp.tool()
def get_headlines(topic: str = "AI technology", limit: int = 5):
    """Fetch latest headlines for a topic via Google News RSS (no API key)."""
    headlines = []
    for entry in feedparser.parse(NEWS_RSS_SEARCH.format(query=quote(topic))).entries[:limit]:
        headlines.append({
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
        })
    log_action("market_news", "get_headlines")
    return headlines

@mcp.tool()
def search_web(query: str, limit: int = 25):
    """News search — used by the chatbot panel. Backed by Google News RSS (no API key)."""
    results = []
    for entry in feedparser.parse(NEWS_RSS_SEARCH.format(query=quote(query))).entries[:limit]:
        source = entry.get("source")
        results.append({
            "title": entry.get("title"),
            "link": entry.get("link"),
            "source": source.get("title") if source else None,
            "published": entry.get("published"),
        })
    log_action("market_news", "search_web")
    return results

if __name__ == "__main__":
    mcp.run()

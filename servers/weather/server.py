# MCP Server: Weather
# Run via: python -m servers.weather.server
# Transport: stdio
# Key teaching moment: synthesize_forecast reconciles two structured forecasts
import os

import requests

from mcp.server.fastmcp import FastMCP
from shared.logger import log_action
from shared.models import WeatherData

mcp = FastMCP("weather")

DEFAULT_LOCATION = "New York,US"


# --- Tools ---

@mcp.tool()
def get_forecast_openweather(location: str):
    """Fetch forecast from OpenWeatherMap (requires OPENWEATHER_API_KEY). Returns WeatherData."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise ValueError("OPENWEATHER_API_KEY environment variable is not set.")
    city = location or os.getenv("WEATHER_LOCATION") or DEFAULT_LOCATION
    resp = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": city, "appid": api_key, "units": "imperial"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    result = WeatherData(
        source="openweathermap",
        temp_f=float(data["main"]["temp"]),
        condition=data["weather"][0]["description"],
        humidity=int(data["main"]["humidity"]),
        forecast=[],
        location=city,
        feels_like_f=float(data["main"].get("feels_like", data["main"]["temp"])),
        wind_mph=float(data.get("wind", {}).get("speed", 0.0)),
        high_f=float(data["main"].get("temp_max", data["main"]["temp"])),
        low_f=float(data["main"].get("temp_min", data["main"]["temp"])),
    )
    log_action("weather", "get_forecast_openweather")
    return result.model_dump()


@mcp.tool()
def get_forecast_wttr(location: str):
    """Fetch forecast from wttr.in (no API key required). Returns WeatherData."""
    city = location or os.getenv("WEATHER_LOCATION") or DEFAULT_LOCATION
    resp = requests.get(f"https://wttr.in/{city}?format=j1", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    current = data["current_condition"][0]
    today = (data.get("weather") or [{}])[0]
    result = WeatherData(
        source="wttr.in",
        temp_f=float(current["temp_F"]),
        condition=current["weatherDesc"][0]["value"],
        humidity=int(current["humidity"]),
        forecast=[],
        location=city,
        feels_like_f=float(current.get("FeelsLikeF", current["temp_F"])),
        wind_mph=float(current.get("windspeedMiles", 0.0)),
        high_f=float(today.get("maxtempF", current["temp_F"])),
        low_f=float(today.get("mintempF", current["temp_F"])),
    )
    log_action("weather", "get_forecast_wttr")
    return result.model_dump()


@mcp.tool()
def synthesize_forecast(location: str):
    """
    Calls both forecast tools internally and reconciles them into one WeatherData.
    Teaching moment: a tool that orchestrates other tools.
    Degrades gracefully — if one source fails (e.g. no API key), it uses the other.
    """
    try:
        owm = get_forecast_openweather(location)
    except Exception:
        owm = None
    try:
        wttr = get_forecast_wttr(location)
    except Exception:
        wttr = None

    available = [f for f in (owm, wttr) if f is not None]
    if not available:
        log_action("weather", "synthesize_forecast", status="error")
        return {"status": "error", "message": "No weather source is available."}

    if len(available) == 1:
        only = available[0]
        unified = dict(only)
        unified["source"] = f"{only['source']} (only available source)"
    else:
        unified = WeatherData(
            source="synthesis (openweathermap + wttr.in)",
            temp_f=round((owm["temp_f"] + wttr["temp_f"]) / 2, 1),
            condition=owm["condition"],  # prefer OWM's wording
            humidity=round((owm["humidity"] + wttr["humidity"]) / 2),
            forecast=[owm, wttr],  # keep both raw sources for transparency
            location=owm.get("location") or wttr.get("location") or "",
            feels_like_f=round((owm["feels_like_f"] + wttr["feels_like_f"]) / 2, 1),
            wind_mph=round((owm["wind_mph"] + wttr["wind_mph"]) / 2, 1),
            high_f=max(owm["high_f"], wttr["high_f"]),
            low_f=min(owm["low_f"], wttr["low_f"]),
        ).model_dump()

    log_action("weather", "synthesize_forecast")
    return unified


if __name__ == "__main__":
    mcp.run()

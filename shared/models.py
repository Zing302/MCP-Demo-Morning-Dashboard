from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class LogEntry(BaseModel):
    timestamp: str
    server: str
    tool: str
    status: str  # "success" | "error"
    duration_ms: Optional[int] = None
    error: Optional[str] = None

class CalendarEvent(BaseModel):
    id: str
    title: str
    date: str  # ISO date "YYYY-MM-DD"
    time: str  # local time-of-day "HH:MM"
    duration_minutes: int
    location: Optional[str] = None

class TodoItem(BaseModel):
    id: str
    title: str
    due: Optional[str] = None
    done: bool = False

class JournalEntry(BaseModel):
    date: str
    content: str
    mood: Optional[str] = None  # "good" | "neutral" | "tough"
    created_at: str

class WeatherData(BaseModel):
    source: str
    temp_f: float
    condition: str
    humidity: int
    forecast: list[dict]
    location: str = ""
    feels_like_f: float = 0.0
    wind_mph: float = 0.0
    high_f: float = 0.0
    low_f: float = 0.0

class StockData(BaseModel):
    ticker: str
    price: float
    change_pct: float
    volume: Optional[int] = None

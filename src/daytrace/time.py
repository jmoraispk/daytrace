from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tzlocal import get_localzone_name

from daytrace.models import DayWindow


def resolve_day(day: date, timezone_name: str | None = None) -> DayWindow:
    name = timezone_name or get_localzone_name()
    zone = ZoneInfo(name)
    start = datetime.combine(day, time.min, zone)
    end = datetime.combine(day + timedelta(days=1), time.min, zone)
    return DayWindow(timezone_name=name, start=start, end=end)

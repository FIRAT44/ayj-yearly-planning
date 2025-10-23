"""
Formatting helpers used across the maintenance planning tab.
"""

from __future__ import annotations

from typing import Optional


def hours_to_minutes(hours: float) -> int:
    return int(round(hours * 60))


def minutes_to_hours(minutes: int) -> float:
    return minutes / 60 if minutes else 0.0


def format_minutes(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    hours, mins = divmod(minutes, 60)
    return f"{sign}{hours:02d}:{mins:02d}"


def format_days(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    return f"{value:+d}" if value < 0 else str(value)

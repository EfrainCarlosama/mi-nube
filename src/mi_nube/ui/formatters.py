from __future__ import annotations

from datetime import datetime


def human_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "—"


def relative_time(value: datetime, now: datetime | None = None) -> str:
    current = now or datetime.now(value.tzinfo)
    if current.tzinfo is None and value.tzinfo is not None:
        current = current.replace(tzinfo=value.tzinfo)
    elif current.tzinfo is not None and value.tzinfo is None:
        value = value.replace(tzinfo=current.tzinfo)
    delta = current - value
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return "Ahora"
    if seconds < 3600:
        return f"Hace {seconds // 60} min"
    if seconds < 86400:
        return f"Hace {seconds // 3600} h"
    days = seconds // 86400
    return f"Hace {days} día" if days == 1 else f"Hace {days} días"

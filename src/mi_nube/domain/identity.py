from __future__ import annotations


def public_display_name(value: str | None, fallback: str = "Cuenta Microsoft") -> str:
    """Return a UI-safe name without exposing an email address."""
    cleaned = (value or "").strip()
    if not cleaned or "@" in cleaned:
        return fallback
    return cleaned

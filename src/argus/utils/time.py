"""Timestamp formatting utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def formatted_timestamp(started_at: Any) -> str:
    if isinstance(started_at, datetime):
        return started_at.astimezone().strftime("%Y%m%d-%H%M%S")
    if isinstance(started_at, str):
        try:
            return datetime.fromisoformat(started_at).astimezone().strftime("%Y%m%d-%H%M%S")
        except ValueError:
            pass
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


__all__ = ["formatted_timestamp"]

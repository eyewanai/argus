"""Safe path component sanitization."""

from __future__ import annotations

import re


def safe_path_component(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "investigation"


__all__ = ["safe_path_component"]

"""Skill models for Argus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    entity_types: tuple[str, ...]
    body: str
    path: Path


__all__ = ["Skill"]

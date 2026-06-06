"""Tiny local tool abstraction for Argus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypedDict


class ToolResult(TypedDict):
    tool_name: str
    input: str
    output: str
    error: str


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    runner: Callable[[str], str]

    def run(self, input: str) -> str:
        return self.runner(input)

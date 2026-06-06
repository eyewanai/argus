"""Tool package for Argus."""

from .base import Tool, ToolResult
from .dns import dns_lookup
from .entity import normalize_entity
from .registry import ToolRegistry, build_tool_registry

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "build_tool_registry",
    "dns_lookup",
    "normalize_entity",
]

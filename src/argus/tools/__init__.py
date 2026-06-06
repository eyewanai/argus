"""Tool package for Argus."""

from .base import Tool, ToolResult
from .dns import dns_a_lookup, dns_mx_lookup, dns_soa_lookup, dns_txt_lookup
from .entity import normalize_entity
from .registration import registration_lookup
from .registry import ToolRegistry, build_tool_registry

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "build_tool_registry",
    "dns_a_lookup",
    "dns_mx_lookup",
    "dns_soa_lookup",
    "dns_txt_lookup",
    "registration_lookup",
    "normalize_entity",
]

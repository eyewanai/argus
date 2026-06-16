"""Infrastructure for future MCP-backed tools."""

from argus.tools.mcp.adapter import build_mcp_result
from argus.tools.mcp.base import MCPToolAdapter
from argus.tools.mcp.models import (
    MCPNormalizedEntity,
    MCPNormalizedFindings,
    MCPNormalizedRelationship,
    MCPNormalizedResult,
)
from argus.tools.mcp.registry import MCPRegistry, build_mcp_registry

__all__ = [
    "MCPNormalizedEntity",
    "MCPNormalizedFindings",
    "MCPNormalizedRelationship",
    "MCPNormalizedResult",
    "MCPRegistry",
    "MCPToolAdapter",
    "build_mcp_registry",
    "build_mcp_result",
]

"""Registry for MCP adapters exposed through the main Argus ToolRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field

from argus.core.config import ArgusConfig
from argus.tools.base import Tool
from argus.tools.mcp.base import MCPToolAdapter


@dataclass(slots=True)
class MCPRegistry:
    adapters: dict[str, MCPToolAdapter] = field(default_factory=dict)

    def register(self, adapter: MCPToolAdapter) -> None:
        if adapter.name in self.adapters:
            raise ValueError(f"MCP adapter '{adapter.name}' is already registered.")
        self.adapters[adapter.name] = adapter

    def has(self, tool_name: str) -> bool:
        return tool_name in self.adapters

    def as_tools(self) -> dict[str, Tool]:
        return {
            tool_name: adapter.as_tool()
            for tool_name, adapter in self.adapters.items()
        }


def build_mcp_registry(config: ArgusConfig) -> MCPRegistry:
    registry = MCPRegistry()
    if not config["tools"]["mcp"]["enabled"]:
        return registry
    return registry

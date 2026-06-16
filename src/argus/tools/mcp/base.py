"""Base interfaces for future MCP-backed Argus tools."""

from __future__ import annotations

from abc import ABC, abstractmethod

from argus.tools.base import Tool, ToolResult
from argus.tools.mcp.adapter import tool_result_to_output


class MCPToolAdapter(ABC):
    name: str
    description: str
    server_name: str

    @abstractmethod
    async def call(self, input_value: str) -> ToolResult:
        """Call an MCP tool and return a fully normalized Argus ToolResult."""

    async def _run(self, input_value: str):
        result = await self.call(input_value)
        return tool_result_to_output(result)

    def as_tool(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            runner=self._run,
        )

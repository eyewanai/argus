"""Generic local tool registry for Argus."""

from __future__ import annotations

from dataclasses import dataclass, field

from argus.config import ArgusConfig
from argus.tools.base import Tool, ToolResult
from argus.tools.dns import dns_lookup


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def run(self, tool_name: str, input: str) -> ToolResult:
        tool = self.tools.get(tool_name)
        if tool is None:
            return {
                "tool_name": tool_name,
                "input": input,
                "output": "",
                "error": f"Tool '{tool_name}' is not registered.",
            }

        try:
            output = tool.run(input)
            return {
                "tool_name": tool_name,
                "input": input,
                "output": output,
                "error": "",
            }
        except Exception as exc:
            return {
                "tool_name": tool_name,
                "input": input,
                "output": "",
                "error": str(exc),
            }


def build_tool_registry(config: ArgusConfig) -> ToolRegistry:
    tools: dict[str, Tool] = {}
    local_config = config["tools"]["local"]
    if local_config["enabled"]:
        available_tools = {
            dns_lookup.name: dns_lookup,
        }
        for tool_name in local_config["include"]:
            tool = available_tools.get(tool_name)
            if tool is not None:
                tools[tool_name] = tool
    return ToolRegistry(tools=tools)

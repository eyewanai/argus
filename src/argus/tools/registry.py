"""Generic local tool registry for Argus."""

from __future__ import annotations

from dataclasses import dataclass, field

from argus.config import ArgusConfig
from argus.tools.base import Tool, ToolResult
from argus.tools.dns import dns_a_lookup, dns_mx_lookup, dns_soa_lookup, dns_txt_lookup
from argus.tools.registration import registration_lookup


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def has(self, tool_name: str) -> bool:
        return tool_name in self.tools

    def available_tools(self) -> list[Tool]:
        return list(self.tools.values())

    def available_tool_names(self) -> list[str]:
        return list(self.tools.keys())

    def available_tool_descriptions(self) -> list[tuple[str, str]]:
        return [(tool.name, tool.description) for tool in self.tools.values()]

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
            dns_a_lookup.name: dns_a_lookup,
            dns_mx_lookup.name: dns_mx_lookup,
            dns_txt_lookup.name: dns_txt_lookup,
            dns_soa_lookup.name: dns_soa_lookup,
            registration_lookup.name: registration_lookup,
        }
        for tool_name in local_config["include"]:
            tool = available_tools.get(tool_name)
            if tool is not None:
                tools[tool_name] = tool
    return ToolRegistry(tools=tools)

"""Generic local tool registry for Argus."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field

from argus.core.cache import ToolCache
from argus.core.config import ArgusConfig
from argus.tools.base import Tool, ToolResult, make_tool_result
from argus.tools.dns.lookup import (
    dns_a_lookup,
    dns_mx_lookup,
    dns_ns_lookup,
    dns_soa_lookup,
    dns_txt_lookup,
    reverse_dns_lookup,
)
from argus.tools.mcp.registry import build_mcp_registry
from argus.tools.tls import tls_certificate_lookup
from argus.tools.whois import registration_lookup


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)
    cache: ToolCache | None = None
    cache_enabled: bool = False
    cache_errors: bool = False
    cache_init_error: str = ""

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
            return make_tool_result(
                tool_name=tool_name,
                input_value=input,
                error=f"Tool '{tool_name}' is not registered.",
            )

        cache_error: str | None = None
        if self.cache_enabled and self.cache is None and self.cache_init_error:
            cache_error = self.cache_init_error
        if self.cache_enabled and self.cache is not None:
            try:
                cached_payload = self.cache.get(tool_name, input)
            except Exception as exc:
                cache_error = str(exc)
            else:
                if isinstance(cached_payload, dict):
                    result = make_tool_result(
                        tool_name=tool_name,
                        input_value=input,
                        output=str(cached_payload.get("output", "")),
                        error=str(cached_payload.get("error", "")),
                        cached=True,
                        normalized=(
                            cached_payload.get("normalized")
                            if isinstance(cached_payload.get("normalized"), dict)
                            else None
                        ),
                        raw=cached_payload.get("raw"),
                        planner_summary=str(cached_payload.get("planner_summary", "")),
                        cache_event=f"Cache hit for {tool_name}({input})",
                    )
                    return result

        try:
            tool_output = tool.run(input)
            if inspect.isawaitable(tool_output):
                tool_output = asyncio.run(tool_output)
            if isinstance(tool_output, dict):
                result = make_tool_result(
                    tool_name=tool_name,
                    input_value=input,
                    output=str(tool_output.get("output", "")),
                    error=str(tool_output.get("error", "")),
                    cached=bool(tool_output.get("cached", False)),
                    normalized=(
                        tool_output.get("normalized")
                        if isinstance(tool_output.get("normalized"), dict)
                        else None
                    ),
                    raw=tool_output.get("raw"),
                    planner_summary=str(tool_output.get("planner_summary", "")),
                )
            else:
                result = make_tool_result(
                    tool_name=tool_name,
                    input_value=input,
                    output=tool_output,
                )
        except Exception as exc:
            result = make_tool_result(
                tool_name=tool_name,
                input_value=input,
                error=str(exc),
            )

        if cache_error:
            result["cache_error"] = f"Cache unavailable: {cache_error}"

        if self.cache_enabled and self.cache is not None:
            should_cache = bool(result["output"]) or (self.cache_errors and bool(result["error"]))
            if should_cache:
                try:
                    self.cache.set(
                        tool_name,
                        input,
                        {
                            "output": result["output"],
                            "error": result["error"],
                            "normalized": result.get("normalized"),
                            "raw": result.get("raw"),
                            "planner_summary": result.get("planner_summary"),
                        },
                    )
                except Exception as exc:
                    result["cache_error"] = f"Cache unavailable: {exc}"
                else:
                    result["cache_event"] = f"Cached result for {tool_name}({input})"

        return result


def build_tool_registry(config: ArgusConfig) -> ToolRegistry:
    tools: dict[str, Tool] = {}
    local_config = config["tools"]["local"]
    if local_config["enabled"]:
        available_tools = {
            dns_a_lookup.name: dns_a_lookup,
            dns_mx_lookup.name: dns_mx_lookup,
            dns_ns_lookup.name: dns_ns_lookup,
            reverse_dns_lookup.name: reverse_dns_lookup,
            dns_txt_lookup.name: dns_txt_lookup,
            dns_soa_lookup.name: dns_soa_lookup,
            registration_lookup.name: registration_lookup,
            tls_certificate_lookup.name: tls_certificate_lookup,
        }
        for tool_name in local_config["include"]:
            tool = available_tools.get(tool_name)
            if tool is not None:
                tools[tool_name] = tool

    mcp_registry = build_mcp_registry(config)
    tools.update(mcp_registry.as_tools())

    cache_config = config["cache"]
    cache: ToolCache | None = None
    cache_init_error = ""
    if cache_config["enabled"]:
        try:
            cache = ToolCache(
                path=cache_config["path"],
                ttl_seconds=cache_config["ttl_seconds"],
            )
        except Exception as exc:
            cache = None
            cache_init_error = str(exc)

    return ToolRegistry(
        tools=tools,
        cache=cache,
        cache_enabled=cache_config["enabled"],
        cache_errors=cache_config["cache_errors"],
        cache_init_error=cache_init_error,
    )

"""Helpers for adapting MCP responses into Argus ToolResult objects."""

from __future__ import annotations

from argus.tools.base import StructuredToolOutput, ToolResult, make_tool_result
from argus.tools.mcp.models import MCPNormalizedFindings, MCPNormalizedResult


def build_mcp_result(
    *,
    tool_name: str,
    input_value: str,
    source: str,
    finding_kind: str,
    query: str,
    summary: dict[str, object] | None = None,
    findings: MCPNormalizedFindings | None = None,
    raw: object = None,
    planner_summary: str,
    output: str = "",
    error: str = "",
) -> ToolResult:
    normalized = MCPNormalizedResult(
        source=source,
        finding_kind=finding_kind,
        query=query,
        summary=summary or {},
        findings=findings or MCPNormalizedFindings(),
    )
    return make_tool_result(
        tool_name=tool_name,
        input_value=input_value,
        output=output,
        error=error,
        normalized=normalized.model_dump(mode="json"),
        raw=raw,
        planner_summary=planner_summary,
    )


def tool_result_to_output(result: ToolResult) -> StructuredToolOutput:
    return {
        "output": result["output"],
        "normalized": result["normalized"],
        "raw": result["raw"],
        "planner_summary": result["planner_summary"],
    }

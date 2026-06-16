"""Tiny local tool abstraction for Argus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, NotRequired, TypedDict

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class NormalizedFindingEntity(TypedDict):
    value: str
    type: str
    parent: str
    relationship: str
    status: NotRequired[str]
    score: NotRequired[float | None]
    classification: NotRequired[str | None]


class NormalizedFindingRelationship(TypedDict):
    source: str
    target: str
    relationship: str


class NormalizedFindings(TypedDict):
    entities: list[NormalizedFindingEntity]
    relationships: list[NormalizedFindingRelationship]
    events: list[str]


class StructuredToolOutput(TypedDict):
    output: str
    normalized: NotRequired[dict[str, JSONValue] | None]
    raw: NotRequired[JSONValue]
    planner_summary: NotRequired[str]


class ToolResult(TypedDict):
    tool_name: str
    input: str
    output: str
    error: str
    cached: bool
    normalized: dict[str, JSONValue]
    raw: JSONValue
    planner_summary: str
    cache_event: NotRequired[str]
    cache_error: NotRequired[str]


type ToolRunnerResult = str | StructuredToolOutput | ToolResult
type ToolRunner = Callable[[str], ToolRunnerResult | Awaitable[ToolRunnerResult]]


def empty_normalized_findings() -> NormalizedFindings:
    return {
        "entities": [],
        "relationships": [],
        "events": [],
    }


def ensure_normalized_payload(
    payload: dict[str, JSONValue] | None,
) -> dict[str, JSONValue]:
    normalized = dict(payload) if isinstance(payload, dict) else {}
    findings = normalized.get("findings")
    if not isinstance(findings, dict):
        normalized["findings"] = empty_normalized_findings()
        return normalized

    entities = findings.get("entities")
    relationships = findings.get("relationships")
    events = findings.get("events")
    normalized["findings"] = {
        "entities": entities if isinstance(entities, list) else [],
        "relationships": relationships if isinstance(relationships, list) else [],
        "events": events if isinstance(events, list) else [],
    }
    return normalized


def make_tool_result(
    *,
    tool_name: str,
    input_value: str,
    output: str = "",
    error: str = "",
    cached: bool = False,
    normalized: dict[str, JSONValue] | None = None,
    raw: JSONValue = None,
    planner_summary: str = "",
    cache_event: str | None = None,
    cache_error: str | None = None,
) -> ToolResult:
    summary = planner_summary.strip()
    if not summary and output.strip():
        summary = output.strip()

    result: ToolResult = {
        "tool_name": tool_name,
        "input": input_value,
        "output": output,
        "error": error,
        "cached": cached,
        "normalized": ensure_normalized_payload(normalized),
        "raw": raw,
        "planner_summary": summary,
    }
    if cache_event:
        result["cache_event"] = cache_event
    if cache_error:
        result["cache_error"] = cache_error
    return result


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    runner: ToolRunner

    def run(self, input: str) -> ToolRunnerResult | Awaitable[ToolRunnerResult]:
        return self.runner(input)

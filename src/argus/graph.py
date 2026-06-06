"""Minimal LangGraph workflow for Argus."""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from argus.config import ArgusConfig, resolve_api_key
from argus.tools import build_tool_registry
from argus.tools import normalize_entity as normalize_entity_tool
from argus.tools.base import ToolResult


class GraphState(TypedDict):
    raw_input: str
    entity: str
    entity_type: str
    notes: str
    next_action: str
    tool_results: list[ToolResult]
    report: str


def _make_client(config: ArgusConfig) -> tuple[OpenAI, str, float]:
    provider = config["providers"][config["default_provider"]]
    api_key = resolve_api_key(provider)
    client = OpenAI(api_key=api_key, base_url=provider["base_url"])
    model = provider["models"]["default"]
    temperature = config["agent"]["temperature"]
    return client, model, temperature


def _fallback_next_action(entity_type: str) -> str:
    return "dns_lookup" if entity_type in {"domain", "url"} else "report"


def _format_tool_results(tool_results: list[ToolResult]) -> str:
    if not tool_results:
        return "- None"

    lines = ["- Tool results:"]
    for result in tool_results:
        lines.append(f"  - Tool: `{result['tool_name']}`")
        lines.append(f"    - Input: `{result['input']}`")
        if result["output"]:
            lines.append("    - Output:")
            for line in result["output"].splitlines():
                lines.append(f"      {line}")
        if result["error"]:
            lines.append(f"    - Error: `{result['error']}`")
    return "\n".join(lines)


def start(state: GraphState) -> GraphState:
    return {
        "raw_input": state["raw_input"],
        "entity": state["entity"],
        "entity_type": state["entity_type"],
        "notes": "",
        "next_action": "",
        "tool_results": [],
        "report": "",
    }


def build_graph(config: ArgusConfig):
    client, model, temperature = _make_client(config)
    tool_registry = build_tool_registry(config)

    def normalize_entity(state: GraphState) -> GraphState:
        normalized = normalize_entity_tool(state["raw_input"])
        return {
            "raw_input": normalized["raw_input"],
            "entity": normalized["entity"],
            "entity_type": normalized["entity_type"],
            "notes": "",
            "next_action": "",
            "tool_results": [],
            "report": "",
        }

    def planner(state: GraphState) -> GraphState:
        fallback_action = _fallback_next_action(state["entity_type"])
        fallback_notes = f"Planner unavailable for `{state['entity']}`."
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise investigation planner. "
                            "Return JSON only with keys notes and next_action. "
                            "next_action must be exactly dns_lookup or report."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Analyze the entity `{state['entity']}` of type `{state['entity_type']}` "
                            "and decide whether DNS lookup is needed."
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            parsed = json.loads(content)
            notes = parsed.get("notes", "")
            next_action = parsed.get("next_action", "")
            if next_action not in {"dns_lookup", "report"}:
                raise ValueError("next_action must be dns_lookup or report.")
        except Exception as exc:
            notes = f"{fallback_notes} {exc}"
            next_action = fallback_action
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": notes.strip(),
            "next_action": next_action,
            "tool_results": [],
            "report": "",
        }

    def route(state: GraphState) -> GraphState:
        return state

    def tool_executor(state: GraphState) -> GraphState:
        result = tool_registry.run(state["next_action"], state["entity"])
        tool_results = list(state["tool_results"])
        tool_results.append(result)
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": state["notes"],
            "next_action": state["next_action"],
            "tool_results": tool_results,
            "report": "",
        }

    def report(state: GraphState) -> GraphState:
        markdown_report = (
            "# Investigation Report\n\n"
            f"- Raw input: `{state['raw_input']}`\n"
            f"- Normalized entity: `{state['entity']}`\n"
            f"- Entity type: `{state['entity_type']}`\n"
            f"- Notes: {state['notes']}\n"
            f"- Selected next action: `{state['next_action']}`\n"
            f"{_format_tool_results(state['tool_results'])}"
        )
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": state["notes"],
            "next_action": state["next_action"],
            "tool_results": state["tool_results"],
            "report": markdown_report,
        }

    graph = StateGraph(GraphState)
    graph.add_node("start", start)
    graph.add_node("normalize_entity", normalize_entity)
    graph.add_node("planner", planner)
    graph.add_node("route", route)
    graph.add_node("tool_executor", tool_executor)
    graph.add_node("report", report)
    graph.add_edge(START, "start")
    graph.add_edge("start", "normalize_entity")
    graph.add_edge("normalize_entity", "planner")
    graph.add_edge("planner", "route")
    graph.add_conditional_edges(
        "route",
        lambda state: (
            "tool_executor"
            if state["next_action"] == "dns_lookup" and state["entity_type"] in {"domain", "url"}
            else "report"
        ),
        {
            "tool_executor": "tool_executor",
            "report": "report",
        },
    )
    graph.add_edge("tool_executor", "report")
    graph.add_edge("report", END)
    return graph.compile()

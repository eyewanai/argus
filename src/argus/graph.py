"""Minimal LangGraph workflow for Argus."""

from __future__ import annotations

import ipaddress
import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from argus.config import ArgusConfig, resolve_api_key
from argus.skills import Skill
from argus.tools import build_tool_registry
from argus.tools import normalize_entity as normalize_entity_tool
from argus.tools.base import ToolResult


class GraphState(TypedDict):
    raw_input: str
    entity: str
    entity_type: str
    notes: str
    next_action: str
    tool_input: str
    skill_name: str
    tool_results: list[ToolResult]
    steps_remaining: int
    report: str


def _make_client(config: ArgusConfig) -> tuple[OpenAI, str, float]:
    provider = config["providers"][config["default_provider"]]
    api_key = resolve_api_key(provider)
    client = OpenAI(api_key=api_key, base_url=provider["base_url"])
    model = provider["models"]["default"]
    temperature = config["agent"]["temperature"]
    return client, model, temperature


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


def _append_note(existing: str, note: str) -> str:
    return note if not existing else f"{existing}\n{note}"


def _append_stop_reason(notes: str, reason: str) -> str:
    return _append_note(notes, f"Stop reason: {reason}")


def _stop_reason(notes: str, next_action: str) -> str:
    for line in reversed(notes.splitlines()):
        if line.startswith("Stop reason: "):
            return line.removeprefix("Stop reason: ")
    if "could not be parsed" in notes.lower():
        return "planner output could not be parsed"
    if "disabled or missing tool" in notes.lower():
        return "selected tool is disabled or missing"
    if "tool input" in notes.lower():
        return "planner did not provide a tool input"
    if "duplicate tool/input pair" in notes.lower():
        return "duplicate tool/input pair"
    if next_action == "report":
        return "planner selected report"
    return "investigation completed"


def _tool_already_used(tool_results: list[ToolResult], tool_name: str, input: str) -> bool:
    return any(
        result["tool_name"] == tool_name and result["input"] == input for result in tool_results
    )


def _first_unused_tool(
    tool_names: list[str],
    tool_results: list[ToolResult],
    input: str,
) -> str | None:
    for tool_name in tool_names:
        if not _tool_already_used(tool_results, tool_name, input):
            return tool_name
    return None


def _extract_ip_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for token in re.findall(r"[0-9A-Fa-f:.]+", text):
        cleaned = token.strip(".,;:()[]{}<>\"'")
        if not cleaned:
            continue
        try:
            normalized = str(ipaddress.ip_address(cleaned))
        except ValueError:
            continue
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _discovered_ip_candidates(tool_results: list[ToolResult]) -> list[str]:
    candidates: list[str] = []
    for result in tool_results:
        for source in (result["input"], result["output"], result["error"]):
            if not source:
                continue
            for candidate in _extract_ip_candidates(source):
                if candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def _first_unused_candidate(
    tool_results: list[ToolResult],
    tool_name: str,
    candidates: list[str],
) -> str:
    for candidate in candidates:
        if not _tool_already_used(tool_results, tool_name, candidate):
            return candidate
    return ""


def _tool_supports_entity(tool_name: str, entity_type: str) -> bool:
    if tool_name == "dns_a_lookup":
        return entity_type in {"domain", "url"}
    if tool_name == "registration_lookup":
        return entity_type in {"domain", "url", "ip"}
    return True


def _fallback_tool_selection(
    state: GraphState,
    enabled_tool_names: list[str],
) -> tuple[str, str]:
    discovered_ips = _discovered_ip_candidates(state["tool_results"])
    for tool_name in enabled_tool_names:
        if not _tool_supports_entity(tool_name, state["entity_type"]):
            continue
        if tool_name == "dns_a_lookup":
            if state["entity_type"] in {"domain", "url"}:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"]],
                )
                if tool_input:
                    return tool_name, tool_input
        elif tool_name == "registration_lookup":
            if state["entity_type"] == "ip":
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"], *discovered_ips],
                )
                if tool_input:
                    return tool_name, tool_input
            if discovered_ips:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    discovered_ips,
                )
                if tool_input:
                    return tool_name, tool_input
            if state["entity_type"] in {"domain", "url"}:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"]],
                )
                if tool_input:
                    return tool_name, tool_input

    for tool_name in enabled_tool_names:
        if not _tool_supports_entity(tool_name, state["entity_type"]):
            continue
        tool_input = _first_unused_candidate(
            state["tool_results"],
            tool_name,
            [state["entity"], state["raw_input"], *discovered_ips],
        )
        if tool_input:
            return tool_name, tool_input

    return "report", ""


def _skill_prompt(skill: Skill | None) -> str:
    if skill is None:
        return ""
    return (
        f"Selected skill: {skill.name}\n"
        f"Skill description: {skill.description}\n"
        "Skill markdown:\n"
        f"{skill.body}"
    )


def start(state: GraphState, max_steps: int, skill_name: str) -> GraphState:
    return {
        "raw_input": state["raw_input"],
        "entity": state["entity"],
        "entity_type": state["entity_type"],
        "notes": "",
        "next_action": "",
        "tool_input": "",
        "skill_name": skill_name,
        "tool_results": [],
        "steps_remaining": max_steps,
        "report": "",
    }


def build_graph(config: ArgusConfig, skill: Skill | None = None):
    client, model, temperature = _make_client(config)
    tool_registry = build_tool_registry(config)
    max_steps = config["agent"]["max_steps"]
    enabled_tool_names = tool_registry.available_tool_names()
    enabled_tool_descriptions = tool_registry.available_tool_descriptions()
    skill_name = skill.name if skill is not None else "none"
    skill_context = _skill_prompt(skill)

    def normalize_entity(state: GraphState) -> GraphState:
        normalized = normalize_entity_tool(state["raw_input"])
        return {
            "raw_input": normalized["raw_input"],
            "entity": normalized["entity"],
            "entity_type": normalized["entity_type"],
            "notes": "",
            "next_action": "",
            "tool_input": "",
            "skill_name": skill_name,
            "tool_results": [],
            "steps_remaining": max_steps,
            "report": "",
        }

    def planner(state: GraphState) -> GraphState:
        enabled_tool_prompt = "\n".join(
            f"- {tool_name}: {description}" for tool_name, description in enabled_tool_descriptions
        )
        fallback_action, fallback_tool_input = _fallback_tool_selection(
            state,
            enabled_tool_names,
        )
        fallback_reason = "no remaining enabled tools."
        if fallback_action != "report":
            fallback_reason = ""
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
                            "Return JSON only with keys notes, next_action, and tool_input. "
                            "next_action must be exactly one enabled tool name or report.\n"
                            "If next_action is a tool, tool_input must be a string to pass to that tool.\n"
                            "If next_action is report, tool_input may be empty.\n"
                            f"{skill_context}\n"
                            "Enabled tools:\n"
                            f"{enabled_tool_prompt or '- None'}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Raw input: `{state['raw_input']}`\n"
                            f"Normalized entity: `{state['entity']}`\n"
                            f"Entity type: `{state['entity_type']}`\n"
                            f"Steps remaining: {state['steps_remaining']}\n"
                            f"Selected skill: `{state['skill_name']}`\n"
                            "Enabled tools:\n"
                            f"{enabled_tool_prompt or '- None'}\n"
                            "Previous tool results:\n"
                            f"{_format_tool_results(state['tool_results'])}\n"
                            "Return JSON only with keys notes, next_action, and tool_input."
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            parsed = json.loads(content)
            notes = parsed.get("notes", "")
            next_action = parsed.get("next_action", "")
            tool_input = parsed.get("tool_input", "")
            if next_action not in {*enabled_tool_names, "report"}:
                raise ValueError("next_action must be an enabled tool name or report.")
            if next_action != "report":
                if not isinstance(tool_input, str) or not tool_input.strip():
                    raise ValueError("tool_input must be provided for tool actions.")
                tool_input = tool_input.strip()
            else:
                tool_input = ""
            notes = notes.strip()
        except Exception as exc:
            if isinstance(exc, json.JSONDecodeError):
                notes = _append_note(
                    state["notes"],
                    f"Stop reason: planner output could not be parsed: {exc}",
                )
                next_action = "report"
                tool_input = ""
            else:
                notes = _append_note(state["notes"], f"{fallback_notes} {exc}")
                if fallback_action == "report" and fallback_reason:
                    notes = _append_stop_reason(notes, fallback_reason)
                next_action = fallback_action
                tool_input = fallback_tool_input
        else:
            notes = _append_note(state["notes"], notes)
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": notes.strip(),
            "next_action": next_action,
            "tool_input": tool_input,
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "report": "",
        }

    def route(state: GraphState) -> GraphState:
        notes = state["notes"]
        next_action = state["next_action"]
        tool_input = state["tool_input"]
        if next_action != "report" and state["steps_remaining"] <= 0:
            notes = _append_stop_reason(notes, "max steps reached.")
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and not tool_registry.has(next_action):
            notes = _append_stop_reason(
                notes,
                f"disabled or missing tool `{next_action}`.",
            )
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and not isinstance(tool_input, str):
            notes = _append_stop_reason(notes, "missing tool input.")
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and not tool_input.strip():
            notes = _append_stop_reason(notes, "missing tool input.")
            next_action = "report"
            tool_input = ""
        elif (
            next_action != "report"
            and next_action.startswith("dns_")
            and state["entity_type"]
            not in {
                "domain",
                "url",
            }
        ):
            notes = _append_stop_reason(
                notes,
                f"`{next_action}` only applies to domain or URL entities.",
            )
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and _tool_already_used(
            state["tool_results"],
            next_action,
            tool_input,
        ):
            notes = _append_stop_reason(
                notes,
                f"duplicate tool/input pair `{next_action}` / `{tool_input}`.",
            )
            next_action = "report"
            tool_input = ""
        elif next_action == "report":
            notes = _append_stop_reason(notes, "planner selected report.")
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": notes,
            "next_action": next_action,
            "tool_input": tool_input,
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "report": state["report"],
        }

    def tool_executor(state: GraphState) -> GraphState:
        result = tool_registry.run(state["next_action"], state["tool_input"])
        tool_results = list(state["tool_results"])
        tool_results.append(result)
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": state["notes"],
            "next_action": state["next_action"],
            "tool_input": state["tool_input"],
            "skill_name": state["skill_name"],
            "tool_results": tool_results,
            "steps_remaining": max(state["steps_remaining"] - 1, 0),
            "report": "",
        }

    def report(state: GraphState) -> GraphState:
        markdown_report = (
            "# Investigation Report\n\n"
            f"- Raw input: `{state['raw_input']}`\n"
            f"- Normalized entity: `{state['entity']}`\n"
            f"- Entity type: `{state['entity_type']}`\n"
            f"- Selected skill: `{state['skill_name']}`\n"
            f"- Notes: {state['notes']}\n"
            f"- Selected next action: `{state['next_action']}`\n"
            f"- Selected tool input: `{state['tool_input']}`\n"
            f"- Stopped because: {_stop_reason(state['notes'], state['next_action'])}\n"
            f"{_format_tool_results(state['tool_results'])}"
        )
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "notes": state["notes"],
            "next_action": state["next_action"],
            "tool_input": state["tool_input"],
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "report": markdown_report,
        }

    graph = StateGraph(GraphState)
    graph.add_node("start", lambda state: start(state, max_steps, skill_name))
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
        lambda state: "tool_executor" if state["next_action"] != "report" else "report",
        {
            "tool_executor": "tool_executor",
            "report": "report",
        },
    )
    graph.add_edge("tool_executor", "planner")
    graph.add_edge("report", END)
    return graph.compile()

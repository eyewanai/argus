"""Rich trace rendering for Argus graph execution."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from argus.core.state import GraphState
from argus.tools.base import ToolResult


def _print_indented(console: Console, text: str, indent: str = "  ") -> None:
    lines = text.splitlines() or [""]
    for line in lines:
        console.print(f"{indent}{line}")


def _tool_label(tool_name: str) -> str:
    labels = {
        "dns_a_lookup": "DNS A Lookup",
        "dns_mx_lookup": "DNS MX Lookup",
        "dns_ns_lookup": "DNS NS Lookup",
        "dns_soa_lookup": "DNS SOA Lookup",
        "dns_txt_lookup": "DNS TXT Lookup",
        "reverse_dns_lookup": "Reverse DNS Lookup",
        "registration_lookup": "Registration Lookup",
        "tls_certificate_lookup": "TLS Certificate Lookup",
    }
    return labels.get(tool_name, tool_name)


def render_update(console: Console, node_name: str, state: GraphState) -> None:
    if node_name == "start":
        return
    if node_name == "normalize_entity":
        console.print("▶ Normalize")
        console.print(f"  Raw input: {state['raw_input']}")
        console.print(f"  Normalized entity: {state['entity']}")
        console.print(f"  Entity type: {state['entity_type']}")
    elif node_name == "planner":
        console.print("▶ Planner")
        console.print(f"  Action selected: {state['next_action']}")
        console.print(f"  Tool input: {state['tool_input']}")
        console.print(f"  Steps remaining: {state['steps_remaining']}")
        console.print(f"  Skill: {state['skill_name']}")
        if state["reasoning_summary"]:
            console.print(f"  Reasoning: {state['reasoning_summary']}")
        if state["stop_reason"]:
            console.print(f"  Stop reason: {state['stop_reason']}")
        if state["events"]:
            console.print(f"  Latest event: {state['events'][-1]}")
        console.print(f"  Pending pivots: {len(state['pending_entities'])}")
    elif node_name == "tool_executor":
        console.print(f"\n▶ {_tool_label(state['next_action'])}")
        result = state["tool_results"][-1] if state["tool_results"] else None
        if result is not None:
            _render_tool_result(console, result)
    elif node_name == "analyze_result":
        console.print("▶ Analyze Result")
        if state["events"]:
            console.print(f"  Latest event: {state['events'][-1]}")
        console.print(f"  Discovered entities: {len(state['discovered_entities'])}")
        console.print(f"  Pending entities: {len(state['pending_entities'])}")
        console.print(f"  Relationships: {len(state['relationships'])}")
    elif node_name == "report":
        console.print("\n▶ Report")
        console.print("\n✓ Investigation complete")


def render_final_report(console: Console, final_state: GraphState) -> None:
    console.print(Markdown(final_state["report"]))


def _render_tool_result(console: Console, result: ToolResult) -> None:
    console.print(f"  Tool: {result['tool_name']}")
    console.print(f"  Input: {result['input']}")
    planner_summary = result.get("planner_summary", "")
    if planner_summary:
        console.print("  Summary:")
        _print_indented(console, planner_summary, indent="    ")
    elif result["output"]:
        console.print("  Output:")
        _print_indented(console, result["output"], indent="    ")
    if result["error"]:
        console.print(f"  Error: {result['error']}")


__all__ = [
    "render_final_report",
    "render_update",
]

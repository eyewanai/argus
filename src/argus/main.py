"""Entry point for the Argus investigation agent."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markdown import Markdown

from argus.config import load_config
from argus.graph import build_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="argus")
    parser.add_argument("entity", nargs="?")
    return parser.parse_args()


def prompt_for_entity() -> str:
    print("Argus")
    print("Enter indicator to investigate:")
    entity = sys.stdin.readline().strip()
    if not entity:
        print("No indicator provided. Exiting.")
        raise SystemExit(1)
    return entity


def _print_indented(console: Console, text: str, indent: str = "  ") -> None:
    lines = text.splitlines() or [""]
    for line in lines:
        console.print(f"{indent}{line}")


def main() -> None:
    console = Console()
    args = parse_args()
    raw_input = args.entity if args.entity else prompt_for_entity()
    config = load_config()
    graph = build_graph(config)
    initial_state = {
        "raw_input": raw_input,
        "entity": raw_input,
        "entity_type": "",
        "notes": "",
        "next_action": "",
        "tool_results": [],
        "report": "",
    }

    console.print("Argus\n")
    final_state = initial_state
    for update in graph.stream(initial_state, stream_mode="updates"):
        node_name, state = next(iter(update.items()))
        final_state = state

        if node_name == "start":
            continue
        if node_name == "normalize_entity":
            console.print("▶ Normalize")
            console.print(f"  Raw input: {state['raw_input']}")
            console.print(f"  Normalized entity: {state['entity']}")
            console.print(f"  Entity type: {state['entity_type']}")
        elif node_name == "planner":
            console.print("▶ Planner")
            console.print(f"  Action selected: {state['next_action']}")
            if state["notes"]:
                console.print(f"  Notes: {state['notes']}")
        elif node_name == "tool_executor":
            console.print("\n▶ Tool Executor")
            result = state["tool_results"][-1] if state["tool_results"] else None
            if result is not None:
                console.print(f"  Tool: {result['tool_name']}")
                console.print(f"  Input: {result['input']}")
                if result["output"]:
                    console.print("  Output:")
                    _print_indented(console, result["output"], indent="    ")
                if result["error"]:
                    console.print(f"  Error: {result['error']}")
        elif node_name == "report":
            console.print("\n▶ Report")
            console.print("\n✓ Investigation complete")

    console.print()
    console.print(Markdown(final_state["report"]))


if __name__ == "__main__":
    main()

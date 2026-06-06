"""Runtime execution helpers for Argus."""

from __future__ import annotations

from rich.console import Console

from argus.config import load_config
from argus.graph import GraphState, build_graph
from argus.skills import Skill
from argus.trace import render_update


def run_investigation(
    console: Console,
    raw_input: str,
    selected_skill: Skill | None,
) -> GraphState:
    config = load_config()
    graph = build_graph(config, skill=selected_skill)
    skill_name = selected_skill.name if selected_skill is not None else "none"
    initial_state: GraphState = {
        "raw_input": raw_input,
        "entity": raw_input,
        "entity_type": "",
        "notes": "",
        "next_action": "",
        "tool_input": "",
        "skill_name": skill_name,
        "tool_results": [],
        "steps_remaining": 0,
        "report": "",
    }

    final_state = initial_state
    for update in graph.stream(initial_state, stream_mode="updates"):
        node_name, state = next(iter(update.items()))
        final_state = state
        render_update(console, node_name, state)
    return final_state


__all__ = [
    "run_investigation",
]

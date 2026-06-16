"""Runtime execution helpers for Argus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console

from argus.core.config import load_config
from argus.core.graph import GraphState, build_graph
from argus.core.trace import render_update
from argus.exporters import write_investigation_artifacts
from argus.skills.models import Skill


@dataclass(frozen=True, slots=True)
class InvestigationRunResult:
    final_state: GraphState
    artifact_paths: list[Path]


def run_investigation(
    console: Console,
    raw_input: str,
    selected_skill: Skill | None,
) -> InvestigationRunResult:
    config = load_config()
    graph = build_graph(config, skill=selected_skill)
    skill_name = selected_skill.name if selected_skill is not None else "none"
    initial_state: GraphState = {
        "raw_input": raw_input,
        "entity": raw_input,
        "entity_type": "",
        "run_started_at": datetime.now().astimezone(),
        "events": [],
        "reasoning_summary": "",
        "next_action": "",
        "tool_input": "",
        "stop_reason": "",
        "skill_name": skill_name,
        "tool_results": [],
        "steps_remaining": 0,
        "discovered_entities": [],
        "pending_entities": [],
        "investigated_entities": [],
        "relationships": [],
        "snapshots": [],
        "report": "",
    }

    final_state = initial_state
    for update in graph.stream(initial_state, stream_mode="updates"):
        node_name, state = next(iter(update.items()))
        final_state = state
        render_update(console, node_name, state)
    artifact_paths = write_investigation_artifacts(final_state, config)
    return InvestigationRunResult(final_state=final_state, artifact_paths=artifact_paths)


__all__ = [
    "InvestigationRunResult",
    "run_investigation",
]

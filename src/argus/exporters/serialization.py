"""JSON-safe serialization helpers for Argus investigation state."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping


def make_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return make_json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "_asdict"):
        return make_json_safe(value._asdict())
    if hasattr(value, "__dict__"):
        return make_json_safe(vars(value))
    return str(value)


def serialize_snapshots(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    snapshots = state.get("snapshots", [])
    safe_snapshots = make_json_safe(snapshots)
    if not isinstance(safe_snapshots, list):
        return []
    return [snapshot for snapshot in safe_snapshots if isinstance(snapshot, dict)]


def serialize_state(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "input": make_json_safe(state.get("raw_input", "")),
        "normalized_entity": make_json_safe(state.get("entity", "")),
        "entity_type": make_json_safe(state.get("entity_type", "unknown")),
        "run_started_at": make_json_safe(state.get("run_started_at")),
        "entities": make_json_safe(state.get("discovered_entities", [])),
        "relationships": make_json_safe(state.get("relationships", [])),
        "tool_runs": make_json_safe(state.get("tool_results", [])),
        "events": make_json_safe(state.get("events", [])),
        "snapshots": serialize_snapshots(state),
        "final_report": make_json_safe(state.get("report", "")),
        "stop_reason": make_json_safe(state.get("stop_reason", "")),
        "skill_name": make_json_safe(state.get("skill_name", "")),
    }

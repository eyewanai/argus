"""Artifact writing for completed investigations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from argus.exporters.markdown import export_report_markdown, export_timeline_markdown
from argus.exporters.mermaid import export_mermaid_graph
from argus.exporters.serialization import serialize_snapshots, serialize_state
from argus.utils import formatted_timestamp, safe_path_component

SUPPORTED_FORMATS = {
    "report.md",
    "timeline.md",
    "graph.mmd",
    "snapshots.json",
    "state.json",
}


def _write_text(path: Path, content: str) -> Path:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def write_investigation_artifacts(
    state: Mapping[str, Any],
    config: Mapping[str, Any],
) -> list[Path]:
    output_config = config.get("output", {})
    if not bool(output_config.get("write_by_default", True)):
        return []

    base_dir = Path(str(output_config.get("dir", "/tmp/argus"))).expanduser()
    run_dir = base_dir / (
        f"{safe_path_component(str(state.get('entity', 'investigation')))}-"
        f"{formatted_timestamp(state.get('run_started_at'))}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    formats = [
        item
        for item in output_config.get("formats", [])
        if isinstance(item, str) and item in SUPPORTED_FORMATS
    ]
    if not formats:
        formats = sorted(SUPPORTED_FORMATS)

    writers: dict[str, str] = {
        "report.md": export_report_markdown(state),
        "timeline.md": export_timeline_markdown(state),
        "graph.mmd": export_mermaid_graph(state),
        "snapshots.json": json.dumps(serialize_snapshots(state), indent=2, ensure_ascii=False),
        "state.json": json.dumps(serialize_state(state), indent=2, ensure_ascii=False),
    }

    written_paths: list[Path] = []
    for format_name in formats:
        written_paths.append(_write_text(run_dir / format_name, writers[format_name]))
    return written_paths

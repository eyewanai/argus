"""Markdown exporters for investigation artifacts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from argus.exporters.mermaid import export_mermaid_graph


def _started_at_text(state: Mapping[str, Any]) -> str:
    started_at = state.get("run_started_at")
    if isinstance(started_at, datetime):
        return started_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(started_at, str) and started_at.strip():
        return started_at
    return "unknown"


def _markdown_table_cell(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    return text.replace("\n", "<br/>").replace("|", "\\|")


def _tool_run_summary(result: Mapping[str, Any]) -> str:
    error = str(result.get("error", "") or "").strip()
    if error:
        return error
    planner_summary = str(result.get("planner_summary", "") or "").strip()
    if planner_summary:
        planner_lines = [line.removeprefix("- ").strip() for line in planner_summary.splitlines()[1:4]]
        summary = "; ".join(line for line in planner_lines if line)
        return summary or planner_summary.splitlines()[0].strip()
    output = str(result.get("output", "") or "").strip()
    if not output:
        return "-"
    first_line = output.splitlines()[0].strip()
    return first_line if len(first_line) <= 160 else f"{first_line[:157]}..."


def _extract_report_summary(final_report: str) -> str:
    match = re.search(r"## Summary\s+(.*?)(?:\n## |\Z)", final_report, flags=re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _build_key_findings(state: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    tool_results = state.get("tool_results", [])
    relationships = state.get("relationships", [])
    pending_entities = state.get("pending_entities", [])

    for result in tool_results:
        if not isinstance(result, Mapping):
            continue
        tool_name = str(result.get("tool_name", "tool"))
        tool_input = str(result.get("input", ""))
        summary = _tool_run_summary(result)
        findings.append(f"`{tool_name}` on `{tool_input}`: {summary}")

    if relationships:
        findings.append(
            f"Mapped {len(relationships)} relationships across the normalized investigation graph."
        )
    if pending_entities:
        findings.append(
            f"Queue still contains {len(pending_entities)} entities for future pivots."
        )

    deduped: list[str] = []
    for finding in findings:
        if finding not in deduped:
            deduped.append(finding)
    return deduped[:6]


def export_timeline_markdown(state: Mapping[str, Any]) -> str:
    entity = str(state.get("entity", "unknown"))
    lines = [
        f"# Investigation Timeline: {entity}",
        "",
        f"Started: {_started_at_text(state)}",
        "",
        "## Timeline",
        "",
    ]
    events = state.get("events", [])
    if not events:
        lines.append("- No investigation events recorded.")
    else:
        for event in events:
            lines.append(f"- {event}")
    return "\n".join(lines)


def export_report_markdown(state: Mapping[str, Any]) -> str:
    entity = str(state.get("entity", "unknown"))
    final_report = str(state.get("report", "") or "")
    summary = _extract_report_summary(final_report)
    if not summary:
        summary = f"Investigation completed for `{entity}`."

    key_findings = _build_key_findings(state)
    mermaid_graph = export_mermaid_graph(state)

    lines = [
        f"# Investigation Report: {entity}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Key Findings",
        "",
    ]
    if not key_findings:
        lines.append("- No significant findings recorded.")
    else:
        lines.extend(f"- {finding}" for finding in key_findings)

    lines.extend(
        [
            "",
            "## Graph",
            "",
            "```mermaid",
            mermaid_graph,
            "```",
            "",
            "## Entities",
            "",
            "| Entity | Type | Status | Source | Score |",
            "| ------ | ---- | ------ | ------ | ----- |",
        ]
    )

    entities = state.get("discovered_entities", [])
    if not entities:
        lines.append("| - | - | - | - | - |")
    else:
        for entity_record in entities:
            if not isinstance(entity_record, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_cell(entity_record.get("value")),
                        _markdown_table_cell(entity_record.get("type", "unknown")),
                        _markdown_table_cell(entity_record.get("status")),
                        _markdown_table_cell(entity_record.get("parent")),
                        _markdown_table_cell(entity_record.get("score")),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Relationships",
            "",
            "| Source | Relationship | Target |",
            "| ------ | ------------ | ------ |",
        ]
    )

    relationships = state.get("relationships", [])
    if not relationships:
        lines.append("| - | - | - |")
    else:
        for relationship in relationships:
            if not isinstance(relationship, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_table_cell(relationship.get("source")),
                        _markdown_table_cell(relationship.get("relationship", "unknown")),
                        _markdown_table_cell(relationship.get("target")),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Tool Runs",
            "",
            "| Step | Tool | Input | Cached | Summary |",
            "| ---- | ---- | ----- | ------ | ------- |",
        ]
    )

    tool_results = state.get("tool_results", [])
    if not tool_results:
        lines.append("| - | - | - | - | - |")
    else:
        for index, result in enumerate(tool_results, start=1):
            if not isinstance(result, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(index),
                        _markdown_table_cell(result.get("tool_name")),
                        _markdown_table_cell(result.get("input")),
                        _markdown_table_cell(result.get("cached", False)),
                        _markdown_table_cell(_tool_run_summary(result)),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Timeline",
            "",
            "See `timeline.md`.",
            "",
            "## Debug Artifacts",
            "",
            "- `state.json`",
            "- `snapshots.json`",
            "- `graph.mmd`",
            "- Raw registration payload remains available in `state.json`.",
        ]
    )

    return "\n".join(lines)

"""Mermaid graph export for investigation relationships."""

from __future__ import annotations

import re
from typing import Any, Mapping


def _safe_node_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    if not slug:
        slug = "unknown"
    if slug[0].isdigit():
        slug = f"node_{slug}"
    return slug


def _safe_label(value: str) -> str:
    return value.replace('"', '\\"')


def export_mermaid_graph(state: Mapping[str, Any]) -> str:
    discovered_entities = state.get("discovered_entities", [])
    relationships = state.get("relationships", [])

    ordered_nodes: list[tuple[str, str]] = []
    node_types: dict[str, str] = {}

    for entity in discovered_entities:
        if not isinstance(entity, Mapping):
            continue
        value = str(entity.get("value", "")).strip()
        if not value:
            continue
        entity_type = str(entity.get("type", "unknown") or "unknown")
        if value not in node_types:
            node_types[value] = entity_type
            ordered_nodes.append((value, entity_type))

    for relationship in relationships:
        if not isinstance(relationship, Mapping):
            continue
        for field in ("source", "target"):
            value = str(relationship.get(field, "")).strip()
            if value and value not in node_types:
                node_types[value] = "unknown"
                ordered_nodes.append((value, "unknown"))

    used_ids: set[str] = set()
    node_ids: dict[str, str] = {}
    for value, _entity_type in ordered_nodes:
        candidate = _safe_node_id(value)
        suffix = 2
        while candidate in used_ids:
            candidate = f"{_safe_node_id(value)}_{suffix}"
            suffix += 1
        used_ids.add(candidate)
        node_ids[value] = candidate

    lines = ["graph TD"]
    for value, entity_type in ordered_nodes:
        node_id = node_ids[value]
        lines.append(f'  {node_id}["{_safe_label(value)}<br/>{_safe_label(entity_type)}"]')

    seen_edges: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        if not isinstance(relationship, Mapping):
            continue
        source = str(relationship.get("source", "")).strip()
        target = str(relationship.get("target", "")).strip()
        rel_type = str(relationship.get("relationship", "unknown") or "unknown").strip()
        if not source or not target:
            continue
        edge = (source, target, rel_type or "unknown")
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        lines.append(
            f"  {node_ids[source]} -->|{_safe_label(rel_type or 'unknown')}| {node_ids[target]}"
        )

    return "\n".join(lines)

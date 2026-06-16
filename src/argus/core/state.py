"""Investigation state type definitions for Argus."""

from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict

from argus.tools.base import ToolResult

QUEUEABLE_ENTITY_TYPES = frozenset({"domain", "ip", "hostname", "nameserver", "email"})
NON_QUEUEABLE_ENTITY_TYPES = frozenset(
    {
        "network",
        "country",
        "rir",
        "registrar",
        "organization",
        "status",
        "description",
    }
)


class EntityRecord(TypedDict):
    value: str
    type: str
    source_tool: str
    parent: str
    status: str
    relationship: str
    score: NotRequired[float | None]
    classification: NotRequired[str | None]


class RelationshipRecord(TypedDict):
    source: str
    target: str
    relationship: str


class ExtractionResult(TypedDict):
    entities: list[EntityRecord]
    relationships: list[RelationshipRecord]
    events: list[str]


class SnapshotSelectedRecord(TypedDict):
    entity: str
    tool: str
    reason: str


class SnapshotQueueRecord(TypedDict):
    entity: str
    type: str
    status: str
    source: str
    score: NotRequired[float | None]
    classification: NotRequired[str | None]


class SnapshotRecord(TypedDict):
    step: int
    selected: SnapshotSelectedRecord
    queue: list[SnapshotQueueRecord]
    entities_count: int
    relationships_count: int
    tool_runs_count: int


class GraphState(TypedDict):
    raw_input: str
    entity: str
    entity_type: str
    run_started_at: datetime
    events: list[str]
    reasoning_summary: str
    next_action: str
    tool_input: str
    stop_reason: str
    skill_name: str
    tool_results: list[ToolResult]
    steps_remaining: int
    discovered_entities: list[EntityRecord]
    pending_entities: list[EntityRecord]
    investigated_entities: list[str]
    relationships: list[RelationshipRecord]
    snapshots: list[SnapshotRecord]
    report: str


__all__ = [
    "EntityRecord",
    "ExtractionResult",
    "GraphState",
    "NON_QUEUEABLE_ENTITY_TYPES",
    "QUEUEABLE_ENTITY_TYPES",
    "RelationshipRecord",
    "SnapshotQueueRecord",
    "SnapshotRecord",
    "SnapshotSelectedRecord",
]

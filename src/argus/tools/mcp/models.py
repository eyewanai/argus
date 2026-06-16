"""Normalized MCP result models for the Argus tool pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class MCPNormalizedEntity(BaseModel):
    value: str
    type: str
    parent: str
    relationship: str
    status: str = "pending"
    score: float | None = None
    classification: str | None = None


class MCPNormalizedRelationship(BaseModel):
    source: str
    target: str
    relationship: str


class MCPNormalizedFindings(BaseModel):
    entities: list[MCPNormalizedEntity] = Field(default_factory=list)
    relationships: list[MCPNormalizedRelationship] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)


class MCPNormalizedResult(BaseModel):
    schema_version: str = "argus.normalized.findings.v1"
    source: str
    finding_kind: str
    query: str
    summary: dict[str, JSONValue] = Field(default_factory=dict)
    findings: MCPNormalizedFindings = Field(default_factory=MCPNormalizedFindings)

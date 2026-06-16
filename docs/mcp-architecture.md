# MCP Architecture

Argus does not connect to MCP servers yet. This document defines the integration contract so future MCP-backed tools can be added without changing `graph.py`, planner logic, queue logic, or exporters.

## Why An Adapter Layer Exists

MCP servers are external systems and can return arbitrary payloads. Argus should never consume MCP responses directly inside the graph.

The MCP adapter is the only layer allowed to understand the MCP server response format:

MCP Server
↓
MCP Adapter
↓
ToolResult
↓
Graph Pipeline

The adapter converts any MCP payload into a standard Argus `ToolResult`.

## ToolResult Contract

Every Argus tool source must return the same contract:

```python
class ToolResult:
    tool_name: str
    input: str
    output: str
    normalized: dict
    raw: JSONValue
    planner_summary: str
```

Field rules:

- `output`: human-readable result for trace/report UX
- `normalized`: the only payload used by entity extraction, relationships, graph, queue, Mermaid export, and report structure
- `raw`: debug-only payload preserved for reproducibility and state export
- `planner_summary`: the only tool payload injected into planner context

Hard rules:

- Graph logic never reads `raw`
- Graph pivot extraction never reads `output`
- Planner never reads `raw`
- Planner reads `planner_summary`, not arbitrary `output`

## Normalized Findings Contract

Every future tool, regardless of source, should emit normalized findings inside `ToolResult.normalized`.

Required shape:

```python
{
  "finding_kind": "...",
  "query": "...",
  "summary": {...},
  "findings": {
    "entities": [
      {
        "value": "example.com",
        "type": "domain",
        "parent": "91.239.26.99",
        "relationship": "passive_resolves_to",
        "status": "pending",
        "score": 0.8,
        "classification": "passive_dns_domain"
      }
    ],
    "relationships": [
      {
        "source": "91.239.26.99",
        "target": "example.com",
        "relationship": "passive_resolves_to"
      }
    ],
    "events": [
      "Observed passive DNS domain example.com for 91.239.26.99"
    ]
  }
}
```

This makes the graph source-agnostic:

Indicator
↓
Tool
↓
ToolResult
↓
Entity Extraction
↓
Relationships
↓
Graph

`graph.py` does not need to know whether a result came from a local tool, MCP tool, API tool, or plugin. It only needs `normalized.findings`.

## MCP Package Layout

```text
src/argus/tools/mcp/
├── __init__.py
├── adapter.py
├── base.py
├── registry.py
└── models.py
```

Responsibilities:

- `base.py`: abstract `MCPToolAdapter`
- `adapter.py`: helper for building normalized `ToolResult` objects from MCP responses
- `models.py`: normalized MCP result models, including generic findings/entities/relationships
- `registry.py`: MCP adapter registry that feeds the main `ToolRegistry`

## Adapter Design

`MCPToolAdapter` owns the MCP-specific normalization boundary:

```python
class MCPToolAdapter(ABC):
    name: str

    async def call(self, input_value: str) -> ToolResult:
        ...
```

Important detail:

- The adapter is async because future MCP calls may be network-bound.
- `ToolRegistry.run()` remains synchronous for the graph and hides async execution internally.
- The runtime registry remains one unified registry for local tools and MCP-backed tools.

## Registry Design

Chosen design: one runtime `ToolRegistry` containing local tools plus MCP-backed tools.

Reasoning:

- Lower complexity for planner: one enabled tool list
- Lower complexity for graph: one execution path
- Lower complexity for cache: one cache contract keyed by tool name and input
- No need for `if source == mcp` branches anywhere in the pipeline

`MCPRegistry` exists only as a staging layer for adapter registration. It feeds standard `Tool` instances into the existing `ToolRegistry`.

## Queue Integration

Queue policy remains entity-type based, not tool-name based.

Correct:

- `queueable(domain)`
- `queueable(ip)`
- `queueable(hostname)`

Incorrect:

- `if tool == passive_dns`
- `if tool == shodan`
- `if tool == mcp_*`

That rule is what allows future MCP findings to enter the same queue without queue logic changes.

## Graph Integration

Entity extraction must operate on `normalized.findings`.

There must be no special handling like:

```python
if tool == "mcp_passive_dns_lookup":
    ...
```

Future tools should provide their graph-ready findings in normalized form so the existing pipeline can:

1. read entities
2. apply queue policy by entity type
3. merge relationships
4. export the same state via Markdown, Mermaid, and JSON

## Future MCP Examples

The following tool classes should fit this architecture without changing graph/planner/queue/exporters:

- Passive DNS
- VirusTotal
- SecurityTrails
- Shodan
- OTX

Example Passive DNS model:

`raw`

```json
{
  "records": [
    {
      "fqdn": "example.com"
    }
  ]
}
```

`normalized.summary`

```json
{
  "query": "91.239.26.99",
  "records": [
    {
      "domain": "example.com",
      "first_seen": "2026-06-01T00:00:00Z",
      "last_seen": "2026-06-13T00:00:00Z"
    }
  ]
}
```

`planner_summary`

```text
Passive DNS for 91.239.26.99:
- example.com
```

`normalized.findings`

```json
{
  "entities": [
    {
      "value": "example.com",
      "type": "domain",
      "parent": "91.239.26.99",
      "relationship": "passive_resolves_to",
      "status": "pending"
    }
  ],
  "relationships": [
    {
      "source": "91.239.26.99",
      "target": "example.com",
      "relationship": "passive_resolves_to"
    }
  ],
  "events": [
    "Observed passive DNS domain example.com for 91.239.26.99"
  ]
}
```

Because the graph consumes only `normalized.findings`, adding Passive DNS through MCP does not require changes to `graph.py`.

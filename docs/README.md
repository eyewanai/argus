# Argus Documentation

## Navigation

| Document | Purpose |
|---|---|
| [architecture.md](architecture.md) | High-level architecture, project structure, dependencies, graph nodes and edges |
| [investigation-flow.md](investigation-flow.md) | Step-by-step flow from user input to final report, with file/function references |
| [investigation-memory.md](investigation-memory.md) | Investigation memory fields, pivot discovery, status transitions, and relationship tracking |
| [state.md](state.md) | Complete state model — every field, who writes it, who reads it, example values |
| [tools.md](tools.md) | All tools, their input/output, configuration, how to add new ones |
| [planner.md](planner.md) | Planner prompt, response schema, fallback logic, stop conditions |
| [reporting.md](reporting.md) | Report structure, section-by-section explanation, current strengths and weaknesses |
| [mcp-architecture.md](mcp-architecture.md) | Future MCP adapter layer and normalized findings contract |

## Quick Reference

### Source Files

| File | Responsibility |
|---|---|
| `src/argus/main.py` | Entry point, wraps `run_cli()` with Ctrl+C handling |
| `src/argus/cli.py` | CLI argument parsing, interactive prompt, skill selection |
| `src/argus/config.py` | Config loading, validation, deep-merge with defaults, provider resolution |
| `src/argus/skills.py` | Skill loading from `~/.config/argus/skills/*/SKILL.md` |
| `src/argus/graph.py` | LangGraph workflow — nodes, state type, investigation memory, extraction, and report generation |
| `src/argus/runner.py` | Graph compilation and streaming execution |
| `src/argus/trace.py` | Rich-based trace output and final Markdown report rendering |
| `src/argus/tools/__init__.py` | Tool package exports |
| `src/argus/tools/base.py` | `Tool` dataclass and `ToolResult` TypedDict |
| `src/argus/tools/registry.py` | `ToolRegistry` — register, query, and run tools |
| `src/argus/tools/entity.py` | Entity normalization (domain, URL, IP, unknown) |
| `src/argus/tools/dns.py` | DNS A/AAAA/MX/SOA/TXT lookup tools |
| `src/argus/tools/registration.py` | WHOIS with RDAP fallback registration lookup |
| `scripts/draw_graph.py` | Generates Mermaid and PNG graphs of the compiled LangGraph |

### Graph Nodes (execution order)

1. `start` — initialize state
2. `normalize_entity` — normalize raw input
3. `planner` — LLM decides next action
4. `route` — validate planner decision
5. `tool_executor` — run selected tool
6. `analyze_result` — discover pivots and relationships from the latest tool result
7. `report` — generate Markdown report (terminate)

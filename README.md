# Argus

Argus is an autonomous investigation agent built with LangGraph.

It explores entities, collects evidence, validates hypotheses, and produces structured reports.

Status: early development.

## Implemented

- **DNS lookup**: A, AAAA, MX, NS, SOA, TXT record resolution via dnspython
- **Registration lookup**: WHOIS with RDAP fallback for domains and IPs
- **TLS certificate lookup**: SAN-domain pivots via standard-library TLS handshake
- **Reverse DNS lookup**: PTR hostname pivots for IP addresses
- **Entity normalization**: domain, URL, and IP extraction from raw input
- **LLM planner**: tool selection with input generation and fallback logic
- **Investigation memory**: discovered entities, pending pivots, investigated entities, and relationships
- **SQLite tool cache**: optional TTL-based caching for shared tool executions
- **Tool registry**: configurable, extensible, with duplicate detection
- **CLI**: interactive prompt and argument-driven modes with Rich output
- **Graph visualization**: LangGraph diagram via `make graph`

## Start Here

- Run `uv run argus nejva.me`
- Architecture overview: [`docs/architecture.md`](docs/architecture.md)
- Track work in [`TODO.md`](TODO.md)

## Investigation Artifacts

Argus now writes deterministic investigation artifacts by default into `/tmp/argus/<safe-entity>-<timestamp>/`.

Files include:

- `report.md`
- `timeline.md`
- `graph.mmd`
- `snapshots.json`
- `state.json`

See [`docs/artifacts.md`](docs/artifacts.md) for the file formats, configuration, and examples.
See [`docs/registration-normalization.md`](docs/registration-normalization.md) for how WHOIS/RDAP raw data is normalized before it reaches the planner, queue, and graph.

## Current Investigation Tools

- `dns_a_lookup`
- `dns_mx_lookup`
- `dns_soa_lookup`
- `dns_txt_lookup`
- `dns_ns_lookup`
- `registration_lookup`
- `tls_certificate_lookup`
- `reverse_dns_lookup`

## Developer Onboarding

### Where to Start Reading Code

| File | Why read it |
|---|---|
| `src/argus/app/cli.py` | Entry point — understand how input arrives |
| `src/argus/app/runner.py` | How the graph is run with streaming |
| `src/argus/core/graph.py` | **The core** — all nodes, state, edges, and report generation |
| `docs/investigation-memory.md` | Investigation memory model and pivot discovery rules |
| `src/argus/core/config.py` | Config schema, loading, and provider setup |
| `src/argus/tools/registry.py` | How tools are registered and built |
| `src/argus/tools/dns/lookup.py` | Example of a concrete tool implementation |
| `src/argus/tools/whois/lookup.py` | WHOIS/RDAP registration lookup tool |

### How to Run the Agent

```bash
# With a domain argument
uv run argus example.com

# With a specific skill
uv run argus example.com --skill domain-investigation

# Pipe input
echo "example.com" | uv run argus
```

### How to Add a New Tool

1. Create a tool module in `src/argus/tools/` that takes `str` and returns `str`
2. Wrap it as a `Tool` dataclass: `my_tool = Tool(name="x", description="...", runner=fn)`
3. Export from `src/argus/tools/__init__.py`
4. Register it in `build_tool_registry()` in `src/argus/tools/registry.py`
5. Add its name to `tools.local.include` in `~/.config/argus/config.json`
6. If the tool has entity type restrictions, update `_tool_supports_entity()` in `src/argus/core/graph.py`

### How to Enable Tool Caching

Add a `cache` section to `~/.config/argus/config.json`:

```json
{
  "cache": {
    "enabled": true,
    "ttl_seconds": 3600,
    "path": "~/.cache/argus/tool_cache.sqlite",
    "cache_errors": false
  }
}
```

- `enabled`: globally turns cache reads/writes on or off
- `ttl_seconds`: cache entry lifetime in seconds
- `path`: SQLite database path; parent directories are created automatically
- `cache_errors`: caches failed tool executions when set to `true`

Default behavior when the section is omitted:

```json
{
  "cache": {
    "enabled": false,
    "ttl_seconds": 3600,
    "path": "~/.cache/argus/tool_cache.sqlite",
    "cache_errors": false
  }
}
```

The default database path is `~/.cache/argus/tool_cache.sqlite`. Expired entries are ignored on read. To clear the cache manually, remove the SQLite file:

```bash
rm ~/.cache/argus/tool_cache.sqlite
```

You can verify cache hits by running the same investigation twice within the TTL and checking for `Cache hit for ...` events in the timeline or trace output.

### How to Add a New Graph Node

1. Define the node function inside `build_graph()` in `src/argus/core/graph.py`
2. It receives `state: GraphState` and returns `GraphState`
3. Register with `graph.add_node("node_name", fn)`
4. Add edges: `graph.add_edge(from, to)` or `graph.add_conditional_edges(from, router, mapping)`
5. If the node needs console output, add a render case in `src/argus/core/trace.py`

### How to Modify Planner Behavior

- **System prompt**: edit the `"content"` string in the system message at `src/argus/core/graph.py`
- **User prompt**: edit the `"content"` string in the user message at `src/argus/core/graph.py`
- **Response schema**: change the keys parsed from the planner response
- **Fallback logic**: modify `_fallback_tool_selection()` at `src/argus/core/graph.py`
- **Duplicate detection**: modify `_tool_already_used()` at `src/argus/core/graph.py`
- **Skill prompt injection**: modify `_skill_prompt()` at `src/argus/core/graph.py`

### How to Modify Report Output

- **Report structure**: edit the `markdown_report` f-string in `report()` at `src/argus/core/graph.py`
- **Summary**: modify `_report_summary()` at `src/argus/core/graph.py`
- **Key findings**: modify `_key_findings()` at `src/argus/core/graph.py`
- **Registration section**: modify `_registration_summaries()` at `src/argus/core/graph.py`
- **Infrastructure section**: modify `_infrastructure_summaries()` at `src/argus/core/graph.py`
- **Raw tool output**: modify `_raw_tool_output()` at `src/argus/core/graph.py`

### Investigation-oriented execution flow

```text
normalize_entity
-> planner
-> route
-> tool_executor
-> analyze_result
-> planner
```

The `analyze_result` node is where Argus turns tool output into discovered pivots and relationships. It does not make network requests.

### How to Add a New State Field

1. Add the field to the `GraphState` TypedDict at `src/argus/core/state.py`
2. Initialize it in the initial state in `src/argus/app/runner.py`
3. Pass it through every node's return dict
4. Add rendering for it in `src/argus/core/trace.py` if it should be visible in traces

## Documentation

Detailed documentation is in the `docs/` directory:

| File | Covers |
|---|---|
| `docs/architecture.md` | High-level architecture, project structure, key dependencies |
| `docs/investigation-flow.md` | Step-by-step flow from input to report |
| `docs/state.md` | All state fields, who reads/writes them |
| `docs/tools.md` | All tools, their input/output, how to add new ones |
| `docs/planner.md` | Planner prompt, actions, fallback, stop conditions |
| `docs/reporting.md` | Report structure, sections, strengths and weaknesses |

# Argus

Argus is an autonomous investigation agent built with LangGraph.

It explores entities, collects evidence, validates hypotheses, and produces structured reports.

Status: early development.

## Implemented

- **DNS lookup**: A, AAAA, MX, SOA, TXT record resolution via dnspython
- **Registration lookup**: WHOIS with RDAP fallback for domains and IPs
- **Entity normalization**: domain, URL, and IP extraction from raw input
- **LLM planner**: tool selection with input generation and fallback logic
- **Tool registry**: configurable, extensible, with duplicate detection
- **CLI**: interactive prompt and argument-driven modes with Rich output
- **Graph visualization**: LangGraph diagram via `make graph`

## Start Here

- Run `uv run python -m argus.main`
- Track work in [`TODO.md`](TODO.md)

# Argus TODO

## Milestone 1

- [x] Add a minimal LangGraph workflow
- [x] Add a first tool registry
- [x] Add a basic investigation loop
## Task 2

- [x] Add the first minimal LangGraph graph
- [x] Print a placeholder markdown report from the CLI

## Task 3

- [x] Add the first LLM node
- [x] Read the API key from environment variables

## Task 4

- [x] Add a provider-based config format
- [x] Auto-create the config file if missing
- [x] Support only openai-compatible providers for now

## Task 5

- [x] Add the first local tool node: DNS lookup
- [x] Keep DNS errors explicit and non-fatal

## Task 6

- [x] Introduce a simple local tool abstraction
- [x] Move DNS lookup into `src/argus/tools/dns.py`

## Task 7

- [x] Add LLM-based tool decision routing
- [x] Keep routing output strict and parseable

## Task 8

- [x] Add a minimal interactive prompt
- [x] Keep argument-driven invocation working

## Task 9

- [x] Add Rich-based investigation tracing
- [x] Keep graph behavior unchanged

## Task 10

- [x] Add entity normalization before analysis
- [x] Keep DNS lookup focused on domains and URLs

## Task 11

- [x] Introduce a tool registry
- [x] Add a generic tool executor node
- [x] Add tools config for local and future MCP tools

## Task 12

- [x] Add Ruff and project quality tooling

## Next

- [ ] Add domain investigation tools
- [ ] Add structured report output
- [ ] Add tests for package import and CLI entry points

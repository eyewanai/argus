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

## Task 13

- [x] Clean up interactive CLI header

## Task 14

- [x] Split DNS capabilities into separate tools
- [x] Make DNS tools configurable through the registry

## Task 15

- [x] Add LangGraph visualization support

## Task 16

- [x] Make runtime graph visualization use real config and tool registry

## Next

- [ ] Add domain investigation tools
- [ ] Add structured report output
- [ ] Add tests for package import and CLI entry points

## Task 17

- [x] Add MX and SOA DNS tools
- [x] Expose enabled tools to the planner

## Task 18

- [x] Add registration lookup with WHOIS and RDAP fallback

## Task 19

- [x] Let the planner choose a specific tool input

## Task 20

- [x] Add user-editable skills support

## Task 21

- [x] Add a no-skill option to interactive selection

## Task 22

- [x] Handle Ctrl+C gracefully in the CLI

## Task 23

- [x] Simplify CLI startup with optional skill selection

## Task 24

- [x] Refactor CLI startup into small modules

## Task 23

- [x] Simplify CLI startup with optional skill selection

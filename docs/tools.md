# Tools

## Tool Model

**File:** `src/argus/tools/base.py`

```python
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    runner: Callable[[str], str]
```

Each tool is a frozen dataclass with:
- `name` — unique string identifier (used by the planner)
- `description` — human-readable description (injected into the planner prompt)
- `runner` — synchronous function that takes `str` input and returns `str` output

### ToolResult

```python
class ToolResult(TypedDict):
    tool_name: str
    input: str
    output: str
    error: str
    cached: bool
    normalized: dict[str, JSONValue]
    raw: JSONValue
    planner_summary: str
    cache_event: NotRequired[str]
    cache_error: NotRequired[str]
```

Returned by `ToolRegistry.run()`. `output` is the human-readable result, `normalized` is the only payload used by graph/entity extraction, `raw` is debug-only, and `planner_summary` is the only tool payload used in planner context. `cached` indicates whether the result came from SQLite cache. `cache_event` and `cache_error` are optional metadata used by the graph to append cache-related events.

## Tool Registry

**File:** `src/argus/tools/registry.py`

`ToolRegistry` is a single runtime registry for all tool sources with optional SQLite caching:
- `has(tool_name)` — check if a tool is registered
- `available_tools()` — list all registered `Tool` objects
- `available_tool_names()` — list all registered tool names
- `available_tool_descriptions()` — list `(name, description)` tuples (fed to planner)
- `run(tool_name, input)` — execute a tool, returns `ToolResult`

`build_tool_registry(config)` reads `config["tools"]["local"]["include"]` and registers only listed tools from the available set. Future MCP adapters are also exposed through this same registry, so planner/graph/queue do not need separate MCP branches.

If `config["cache"]["enabled"]` is `true`, `run()` checks `~/.cache/argus/tool_cache.sqlite` by default before executing the real tool. Cache keys are SHA-256 hashes of `tool_name + ":" + normalized_input`, where normalized input is stripped and case-folded.

## Available Tools

### dns_a_lookup

| Attribute | Value |
|---|---|
| **File** | `src/argus/tools/dns.py:105` |
| **Description** | `"Resolve A and AAAA records for a domain or hostname."` |
| **Input** | Domain or hostname string |
| **Output** | Text lines: `- A: 1.2.3.4` / `- AAAA: ::1` or error message |
| **Use when** | You need to discover IP addresses behind a domain |
| **Limitations** | Only works for `domain`/`url` entity types; blocked by `route` for IP entities |

**Example input:** `"example.com"`

**Example output:**
```
- A: 93.184.216.34
- AAAA: 2606:2800:220:1:248:1893:25c8:1946
```

---

### dns_mx_lookup

| Attribute | Value |
|---|---|
| **File** | `src/argus/tools/dns.py:116` |
| **Description** | `"Resolve MX records for a domain or hostname."` |
| **Input** | Domain or hostname string |
| **Output** | Text lines: `- MX: priority 10 exchange mail.example.com.` or error message |
| **Use when** | You need to discover mail servers for a domain |
| **Limitations** | Only works for `domain`/`url` entity types |

**Example input:** `"example.com"`

**Example output:**
```
- MX: priority 10 exchange mail.example.com.
```

---

### dns_soa_lookup

| Attribute | Value |
|---|---|
| **File** | `src/argus/tools/dns.py:122` |
| **Description** | `"Resolve the SOA record for a domain or hostname."` |
| **Input** | Domain or hostname string |
| **Output** | Text lines with mname, rname, serial, refresh, retry, expire, minimum or error message |
| **Use when** | You need authoritative nameserver information for a domain |
| **Limitations** | Only works for `domain`/`url` entity types |

**Example input:** `"example.com"`

**Example output:**
```
- SOA: mname a.iana-servers.net.
- SOA: rname hostmaster.iana-servers.net.
- SOA: serial 2024032000
- SOA: refresh 3600
- SOA: retry 1800
- SOA: expire 604800
- SOA: minimum 3600
```

---

### dns_txt_lookup

| Attribute | Value |
|---|---|
| **File** | `src/argus/tools/dns.py:128` |
| **Description** | `"Resolve TXT records for a domain or hostname."` |
| **Input** | Domain or hostname string |
| **Output** | Text lines: `- TXT: "v=spf1 include:_spf.example.com ~all"` or error message |
| **Use when** | You need SPF, DKIM, DMARC, or other TXT-based records |
| **Limitations** | Only works for `domain`/`url` entity types |

**Example input:** `"example.com"`

**Example output:**
```
- TXT: "v=spf1 include:_spf.example.com ~all"
- TXT: "google-site-verification=..."
```

---

### registration_lookup

| Attribute | Value |
|---|---|
| **File** | `src/argus/tools/registration.py:119` |
| **Description** | `"Look up registration and ownership information for domains and IPs."` |
| **Input** | Domain, URL, or IP string |
| **Output** | JSON blocks prefixed with `WHOIS:` and/or `RDAP:` |
| **Use when** | You need registrar, organization, creation/expiration dates, or IP ownership |
| **Limitations** | WHOIS uses `python-whois` (may return incomplete data for some TLDs); RDAP uses `whoisit` (requires bootstrap, which involves network I/O on first call). IP lookups use RDAP only (no WHOIS for IPs). |

**Example input:** `"example.com"`

**Example output:**
```
WHOIS:
{
  "registrar": "Internet Assigned Numbers Authority",
  "creation_date": "1992-01-01 00:00:00",
  "expiration_date": "2025-01-01 00:00:00",
  "org": "Internet Assigned Numbers Authority"
}
```

**Example IP input:** `"93.184.216.34"`

**Example IP output:**
```
RDAP:
{
  "name": "EDGECAST-NETBLK-03",
  "country": "US",
  "startAddress": "93.184.216.0",
  "endAddress": "93.184.223.255",
  "cidr0_cidrs": [{"v4prefix": "93.184.216.0", "length": 21}]
}
```

## Entity Normalization Tool

**File:** `src/argus/tools/entity.py`

This is NOT a registered tool — it's called directly from the `normalize_entity` graph node.

| Attribute | Value |
|---|---|
| **Function** | `normalize_entity(input: str) -> dict[str, str]` |
| **Input** | Raw user input |
| **Output** | `{"raw_input": str, "entity": str, "entity_type": str}` |
| **Entity types** | `"url"`, `"ip"`, `"domain"`, `"unknown"` |

## How to Add a New Tool

1. Create a new file in `src/argus/tools/` (or add to an existing one)
2. Define a function that takes `str` and returns `str`
3. Create a `Tool` instance: `my_tool = Tool(name="my_tool", description="...", runner=my_func)`
4. Export it from `src/argus/tools/__init__.py`
5. Add it to `available_tools` dict in `src/argus/tools/registry.py` `build_tool_registry()`
6. Add its name to the `include` list in `~/.config/argus/config.json`
7. If the tool has entity type restrictions, add logic to `_tool_supports_entity()` in `graph.py`

## Configuring Tools

In `~/.config/argus/config.json`:

```json
{
  "tools": {
    "local": {
      "enabled": true,
      "include": ["dns_a_lookup", "dns_mx_lookup", "registration_lookup"]
    }
  }
}
```

Only tools listed in `include` are registered and available to the planner.

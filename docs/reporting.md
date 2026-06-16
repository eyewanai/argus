# Report Generation

The `report` node still generates the final Markdown report, but it now includes investigation memory.

## Current structure

```markdown
# Investigation Report

## Summary

## Key Findings

## Registration Information

## Infrastructure

## Discovered Entities

## Relationships

## Investigation Timeline

## Evidence

## Raw Tool Output
```

## New investigation-oriented sections

### `Discovered Entities`

Grouped by type:

- Domains
- Nameservers
- IPs
- Emails
- ASNs

This section is built from `state["discovered_entities"]` plus relationship context, not by re-parsing the report text.

### `Relationships`

Rendered as a simple source-target tree, for example:

```text
phdays.com
  ├─ resolves_to -> 178.248.239.191
  ├─ has_mx -> mx1.phdays.com
  └─ has_nameserver -> ns3.ptsecurity.com
```

This section is built from `state["relationships"]`.

## Why this matters

Before this change, the report only summarized tool outputs. Now it also shows:

- what new pivots were discovered
- why those pivots exist
- how they relate to the original entity

That makes the report reflect an investigation graph rather than a flat DNS/tool transcript.

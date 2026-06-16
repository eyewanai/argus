# Registration Normalization

Raw WHOIS and RDAP normalization lives in `src/argus/tools/whois/`:
- `models.py` — Pydantic models (`NormalizedRegistrationResult`, `RegistrationContact`, etc.)
- `normalize.py` — Raw RDAP/WHOIS to normalized result conversion
- `lookup.py` — `registration_lookup` tool with WHOIS/RDAP execution

Argus keeps raw WHOIS and RDAP responses for debugging, but investigation logic no longer pivots directly on raw registration payloads.

## Why raw WHOIS/RDAP is not used for investigation

Raw registration payloads contain service metadata that is useful for debugging but harmful for graph exploration:

- RDAP service URLs such as `rdap.db.ripe.net`
- WHOIS servers such as `whois.ripe.net`
- legal and terms links such as `www.ripe.net` and `db-terms-conditions.pdf`
- entity URLs and other provider metadata

If these raw values are parsed as pivots, the agent pollutes the queue, planner context, and graph with infrastructure that belongs to the registration service rather than the investigated target.

## Registration flow

Argus now treats registration data as:

```text
registration_lookup
  -> raw_result
  -> normalizer
  -> normalized_result
```

### `raw_result`

- kept in `tool_runs`
- serialized into `state.json`
- available in debug artifacts
- not used for planner context
- not used for entity extraction
- not used for queue construction
- not used for graph edges

### `normalized_result`

- used by planner summaries
- used by entity extraction
- used by queue construction
- used by graph relationships
- used by reports

The generated `report.md` does not embed raw WHOIS/RDAP payloads. Registration sections in reports are derived from normalized summaries and relationship state, while raw payloads remain in `state.json`.

## Normalized IP RDAP fields

For IP RDAP, Argus uses:

- `queried_ip`
- `network`
- `ip_version`
- `country`
- `rir`
- `name`
- `description`
- `assignment_type`
- `handle`
- `parent_handle`
- `registration_date`
- `last_changed_date`
- `expiration_date`
- abuse, admin, technical, and registrant contacts
- `raw_refs` only as debug references

Service/reference metadata such as RDAP URLs, WHOIS servers, and terms URLs is captured in `raw_refs` and preserved for debugging, but it is not converted into queue entities or graph pivots.

## Normalized domain WHOIS/RDAP fields

For domain registration, Argus uses:

- `domain`
- `registrar`
- `registrar_url`
- `registrar_abuse_email`
- `registrar_abuse_phone`
- `registrant_name`
- `registrant_org`
- `registrant_email`
- `registrant_country`
- `admin_email`
- `tech_email`
- `nameservers`
- `status`
- `creation_date`
- `updated_date`
- `expiration_date`

Argus intentionally ignores raw WHOIS server domains, footer URLs, terms links, and arbitrary legal metadata for investigation pivots.

## Effect on graph, queue, and planner

### Planner

The planner sees a short normalized summary such as:

```text
Registration lookup for 91.239.26.99:
- Network: 91.239.26.0/24
- Name: RU-IONICA-CUST-91-239-26-0-24-20160907
- Country: RU
- RIR: RIPE
- Abuse contact: Serveroid LLC <abuse@flops.ru>
```

Raw RDAP JSON is not injected into planner context.

### Graph

The graph is built from normalized relationships such as:

- `91.239.26.99 -> belongs_to_network -> 91.239.26.0/24`
- `91.239.26.0/24 -> has_abuse_contact -> abuse@flops.ru`
- `91.239.26.0/24 -> has_abuse_org -> Serveroid LLC`

### Queue

- network ranges may be preserved as low-priority nodes
- abuse emails can enter the queue
- nameservers can enter the queue
- service/reference domains from raw refs never enter the queue

## Where raw data still exists

Raw registration responses remain available in:

- `tool_runs` inside investigation state
- `state.json`
- debug artifacts written after a run

This keeps the run reproducible without letting raw registration metadata distort the investigation graph.

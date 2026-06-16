"""Minimal LangGraph workflow for Argus."""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from argus.core.config import ArgusConfig, resolve_api_key
from argus.core.state import (
    QUEUEABLE_ENTITY_TYPES,
    EntityRecord,
    ExtractionResult,
    GraphState,
    RelationshipRecord,
    SnapshotQueueRecord,
    SnapshotRecord,
)
from argus.skills.models import Skill
from argus.tools import build_tool_registry
from argus.tools import normalize_entity as normalize_entity_tool
from argus.tools.base import ToolResult

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b", re.IGNORECASE)
ASN_PATTERN = re.compile(r"\bAS(\d{1,10})\b", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
    re.IGNORECASE,
)


def _make_client(config: ArgusConfig) -> tuple[OpenAI, str, float]:
    provider = config["providers"][config["default_provider"]]
    api_key = resolve_api_key(provider)
    client = OpenAI(api_key=api_key, base_url=provider["base_url"])
    model = provider["models"]["default"]
    temperature = config["agent"]["temperature"]
    return client, model, temperature


def _format_tool_results(tool_results: list[ToolResult]) -> str:
    if not tool_results:
        return "- None"

    lines = ["- Tool results:"]
    for result in tool_results:
        lines.append(f"  - Tool: `{result['tool_name']}`")
        lines.append(f"    - Input: `{result['input']}`")
        lines.append(f"    - Cached: `{result.get('cached', False)}`")
        planner_summary = result.get("planner_summary", "")
        if planner_summary:
            lines.append("    - Summary:")
            for line in planner_summary.splitlines():
                lines.append(f"      {line}")
        if result["error"]:
            lines.append(f"    - Error: `{result['error']}`")
    return "\n".join(lines)


def _append_event(events: list[str], event: str) -> list[str]:
    cleaned = event.strip()
    if not cleaned:
        return list(events)
    return [*events, cleaned]


def _build_snapshot(
    state: GraphState,
    next_action: str,
    tool_input: str,
    reasoning_summary: str,
    stop_reason: str,
) -> SnapshotRecord:
    queue: list[SnapshotQueueRecord] = []
    for entity in state["pending_entities"]:
        snapshot_entity: SnapshotQueueRecord = {
            "entity": entity["value"],
            "type": entity["type"],
            "status": entity["status"],
            "source": entity.get("parent", ""),
        }
        snapshot_entity["score"] = entity.get("score")
        snapshot_entity["classification"] = entity.get("classification")
        queue.append(snapshot_entity)

    selected_entity = tool_input if next_action != "report" else state["entity"]
    selected_reason = reasoning_summary or stop_reason or "No reasoning summary provided."
    return {
        "step": len(state["snapshots"]) + 1,
        "selected": {
            "entity": selected_entity,
            "tool": next_action,
            "reason": selected_reason,
        },
        "queue": queue,
        "entities_count": len(state["discovered_entities"]),
        "relationships_count": len(state["relationships"]),
        "tool_runs_count": len(state["tool_results"]),
    }


def start(state: GraphState, max_steps: int, skill_name: str) -> GraphState:
    return {
        "raw_input": state["raw_input"],
        "entity": state["entity"],
        "entity_type": state["entity_type"],
        "run_started_at": state["run_started_at"],
        "events": [],
        "reasoning_summary": "",
        "next_action": "",
        "tool_input": "",
        "stop_reason": "",
        "skill_name": skill_name,
        "tool_results": [],
        "steps_remaining": max_steps,
        "discovered_entities": [],
        "pending_entities": [],
        "investigated_entities": [],
        "relationships": [],
        "snapshots": [],
        "report": "",
    }


def _tool_label(tool_name: str) -> str:
    labels = {
        "dns_a_lookup": "DNS A/AAAA lookup",
        "dns_mx_lookup": "DNS MX lookup",
        "dns_ns_lookup": "DNS NS lookup",
        "dns_soa_lookup": "DNS SOA lookup",
        "dns_txt_lookup": "DNS TXT lookup",
        "reverse_dns_lookup": "reverse DNS lookup",
        "registration_lookup": "registration lookup",
        "tls_certificate_lookup": "TLS certificate lookup",
    }
    return labels.get(tool_name, tool_name)


def _normalized_tool_payload(result: ToolResult) -> dict[str, Any]:
    normalized = result.get("normalized")
    if isinstance(normalized, dict):
        return normalized
    return {}


def _normalized_finding_payload(result: ToolResult) -> dict[str, Any]:
    findings = _normalized_tool_payload(result).get("findings")
    if isinstance(findings, dict):
        return findings
    return {}


def _uses_generic_normalized_findings(result: ToolResult) -> bool:
    normalized = _normalized_tool_payload(result)
    if "finding_kind" in normalized or "schema_version" in normalized:
        return True
    return False


def _extract_ip_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for token in re.findall(r"[0-9A-Fa-f:.]+", text):
        cleaned = token.strip(".,;:()[]{}<>\"'")
        if not cleaned:
            continue
        try:
            normalized = str(ipaddress.ip_address(cleaned))
        except ValueError:
            continue
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _extract_domain_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in DOMAIN_PATTERN.findall(text):
        candidate = match.strip(".,;:()[]{}<>\"'").lower().rstrip(".")
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _extract_email_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in EMAIL_PATTERN.findall(text):
        candidate = match.strip().lower()
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _extract_asn_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in ASN_PATTERN.findall(text):
        candidate = f"AS{int(match)}"
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _canonicalize_entity(value: str, fallback_type: str = "unknown") -> tuple[str, str]:
    candidate = value.strip()
    if not candidate:
        return "", "unknown"

    emails = _extract_email_candidates(candidate)
    if emails:
        return emails[0], "email"

    asns = _extract_asn_candidates(candidate)
    if asns and candidate.upper().startswith("AS"):
        return asns[0], "asn"

    try:
        return str(ipaddress.ip_address(candidate)), "ip"
    except ValueError:
        pass

    domains = _extract_domain_candidates(candidate)
    if domains and domains[0] == candidate.lower().rstrip("."):
        if fallback_type in {"hostname", "nameserver"}:
            return domains[0], fallback_type
        return domains[0], "domain"

    normalized = normalize_entity_tool(candidate)
    entity = normalized["entity"].strip()
    entity_type = normalized["entity_type"]
    if entity_type in {"domain", "url", "ip"} and entity:
        if entity_type == "url":
            return entity.lower(), "domain"
        return entity.lower() if entity_type == "domain" else entity, entity_type

    if fallback_type == "domain":
        return candidate.lower(), "domain"
    if fallback_type in {"hostname", "nameserver"}:
        return candidate.lower(), fallback_type
    if fallback_type == "network":
        return candidate, fallback_type
    return candidate, fallback_type


def _entity_key(entity: EntityRecord) -> tuple[str, str]:
    return entity["value"], entity["type"]


def _relationship_key(relationship: RelationshipRecord) -> tuple[str, str, str]:
    return relationship["source"], relationship["target"], relationship["relationship"]


def entity_type_is_queueable(entity_type: str) -> bool:
    return entity_type in QUEUEABLE_ENTITY_TYPES


def is_queueable_entity(entity: EntityRecord) -> bool:
    return entity.get("status") == "pending" and entity_type_is_queueable(entity["type"])


def _apply_queue_policy(entity: EntityRecord) -> EntityRecord:
    normalized = dict(entity)
    if normalized["status"] == "pending" and not entity_type_is_queueable(normalized["type"]):
        normalized["status"] = "done"
        normalized.pop("score", None)
    return normalized  # type: ignore[return-value]


def _derive_parent_domain(value: str) -> str:
    labels = value.lower().rstrip(".").split(".")
    if len(labels) < 3:
        return ""
    return ".".join(labels[-2:])


def _build_parent_domain_pivot(entity: EntityRecord) -> tuple[EntityRecord, RelationshipRecord, str] | None:
    if entity["type"] not in {"hostname", "nameserver"}:
        return None
    parent_domain = _derive_parent_domain(entity["value"])
    if not parent_domain or parent_domain == entity["value"]:
        return None
    parent_entity = _build_entity(
        parent_domain,
        entity["source_tool"],
        entity["value"],
        "parent_domain",
        fallback_type="domain",
        status="pending",
    )
    if parent_entity is None:
        return None
    parent_entity["score"] = 0.12
    parent_entity["classification"] = "parent_domain"
    relationship: RelationshipRecord = {
        "source": entity["value"],
        "target": parent_entity["value"],
        "relationship": "parent_domain",
    }
    event = f"Discovered parent domain {parent_entity['value']} from {entity['value']}"
    return parent_entity, relationship, event


def _build_entity(
    value: str,
    source_tool: str,
    parent: str,
    relationship: str,
    *,
    status: str = "pending",
    fallback_type: str = "unknown",
) -> EntityRecord | None:
    canonical, entity_type = _canonicalize_entity(value, fallback_type=fallback_type)
    if not canonical:
        return None
    return {
        "value": canonical,
        "type": entity_type,
        "source_tool": source_tool,
        "parent": parent,
        "status": status,
        "relationship": relationship,
    }


def _sync_investigation_views(
    discovered_entities: list[EntityRecord],
) -> tuple[list[EntityRecord], list[str]]:
    pending_entities = [entity for entity in discovered_entities if is_queueable_entity(entity)]
    investigated_entities = [
        entity["value"]
        for entity in discovered_entities
        if entity["status"] == "done"
    ]
    return pending_entities, investigated_entities


def _merge_entity(
    discovered_entities: list[EntityRecord],
    entity: EntityRecord,
) -> tuple[list[EntityRecord], bool]:
    entity = _apply_queue_policy(entity)
    key = _entity_key(entity)
    merged = [dict(item) for item in discovered_entities]
    for index, existing in enumerate(merged):
        if _entity_key(existing) == key:
            if existing["status"] == "done" and entity["status"] != "done":
                return merged, False
            if existing["status"] == "investigating" and entity["status"] == "pending":
                return merged, False
            updated = dict(existing)
            updated["status"] = entity["status"]
            merged[index] = updated  # type: ignore[assignment]
            return merged, False
    merged.append(entity)
    return merged, True


def _set_entity_status(
    discovered_entities: list[EntityRecord],
    value: str,
    status: str,
    *,
    source_tool: str = "",
    parent: str = "",
    relationship: str = "",
    fallback_type: str = "unknown",
) -> tuple[list[EntityRecord], bool]:
    canonical, entity_type = _canonicalize_entity(value, fallback_type=fallback_type)
    if not canonical:
        return [dict(item) for item in discovered_entities], False

    updated_entities = [dict(item) for item in discovered_entities]
    for index, entity in enumerate(updated_entities):
        if entity["value"] == canonical:
            if entity["status"] == status:
                return updated_entities, False
            updated_entity = dict(entity)
            updated_entity["status"] = status
            updated_entities[index] = updated_entity  # type: ignore[assignment]
            return updated_entities, True

    entity: EntityRecord = {
        "value": canonical,
        "type": entity_type,
        "source_tool": source_tool or "planner",
        "parent": parent,
        "status": status,
        "relationship": relationship,
    }
    updated_entities.append(_apply_queue_policy(entity))
    return updated_entities, True


def _merge_relationship(
    relationships: list[RelationshipRecord],
    relationship: RelationshipRecord,
) -> tuple[list[RelationshipRecord], bool]:
    merged = list(relationships)
    key = _relationship_key(relationship)
    if any(_relationship_key(existing) == key for existing in merged):
        return merged, False
    merged.append(relationship)
    return merged, True


def _format_entities_for_prompt(entities: list[EntityRecord], empty_message: str) -> str:
    if not entities:
        return f"- {empty_message}"
    lines = []
    for entity in entities:
        lines.append(
            "- "
            f"{entity['value']} ({entity['type']}, status={entity['status']}, "
            f"via {entity['source_tool']} from {entity['parent'] or 'root'})"
        )
    return "\n".join(lines)


def _format_relationships_for_prompt(
    relationships: list[RelationshipRecord],
    empty_message: str,
) -> str:
    if not relationships:
        return f"- {empty_message}"
    return "\n".join(
        f"- {relationship['source']} -> {relationship['relationship']} -> {relationship['target']}"
        for relationship in relationships
    )


def _dns_source(result: ToolResult) -> str:
    normalized = _normalized_tool_payload(result)
    return str(normalized.get("query", result["input"])).lower()


def _dns_record_type(result: ToolResult) -> str:
    normalized = _normalized_tool_payload(result)
    record_type = normalized.get("record_type")
    if isinstance(record_type, str):
        return record_type.upper()
    return ""


def _dns_record_dicts(result: ToolResult) -> list[dict[str, Any]]:
    normalized = _normalized_tool_payload(result)
    records = normalized.get("records", [])
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _extract_dns_record_entities(result: ToolResult) -> ExtractionResult:
    records = _dns_record_dicts(result)
    if not records:
        return {"entities": [], "relationships": [], "events": []}

    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = []
    source = _dns_source(result)
    seen: set[tuple[str, str, str]] = set()

    for record in records:
        record_type = str(record.get("record_type", "")).upper()
        value = record.get("value")
        if not isinstance(value, str) or not value.strip():
            continue

        fallback_type = "unknown"
        relationship = ""
        classification = ""
        score: float | None = None
        event_template = ""

        if record_type in {"A", "AAAA"}:
            fallback_type = "ip"
            relationship = "resolves_to"
            classification = "resolved_ip"
            score = 0.9
            event_template = "Discovered IP {target} from {source}"
        elif record_type == "NS":
            fallback_type = "nameserver"
            relationship = "has_nameserver"
            classification = "nameserver"
            score = 0.15
            event_template = "Discovered nameserver {target} from {source}"
        elif record_type == "PTR":
            fallback_type = "hostname"
            relationship = "reverse_resolves_to"
            classification = "hostname"
            score = 0.4
            event_template = "Discovered PTR hostname {target} from {source}"
        else:
            continue

        entity = _build_entity(
            value,
            result["tool_name"],
            source,
            relationship,
            fallback_type=fallback_type,
        )
        if entity is None or entity["value"] == source:
            continue

        dedupe_key = (entity["value"], entity["type"], relationship)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        if score is not None:
            entity["score"] = score
        entity["classification"] = classification
        entities.append(entity)
        relationships.append(
            {
                "source": source,
                "target": entity["value"],
                "relationship": relationship,
            }
        )
        events.append(event_template.format(target=entity["value"], source=source))

    return {"entities": entities, "relationships": relationships, "events": events}


def _extract_dns_mx_entities(result: ToolResult) -> ExtractionResult:
    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = []
    source = _dns_source(result)
    exchanges: list[str] = []
    seen_exchanges: set[str] = set()

    records = _dns_record_dicts(result)
    if records:
        for record in records:
            exchange = record.get("exchange")
            if not isinstance(exchange, str) or not exchange.strip():
                continue
            candidate = exchange.strip().lower().rstrip(".")
            if candidate in seen_exchanges:
                continue
            seen_exchanges.add(candidate)
            exchanges.append(candidate)
    else:
        for line in result["output"].splitlines():
            if " exchange " not in line:
                continue
            exchange = line.split(" exchange ", 1)[1].strip().rstrip(".")
            candidate = exchange.lower()
            if candidate in seen_exchanges:
                continue
            seen_exchanges.add(candidate)
            exchanges.append(candidate)

    for exchange in exchanges:
        entity = _build_entity(
            exchange,
            result["tool_name"],
            source,
            "has_mx",
            fallback_type="domain",
        )
        if entity is None or entity["value"] == source:
            continue
        entity["score"] = 0.25
        entity["classification"] = "mx_host"
        entities.append(entity)
        relationships.append(
            {
                "source": source,
                "target": entity["value"],
                "relationship": "has_mx",
            }
        )
        events.append(f"Discovered MX host {entity['value']} from {source}")
    return {
        "entities": entities,
        "relationships": relationships,
        "events": events,
    }


def _extract_dns_a_entities(result: ToolResult) -> ExtractionResult:
    extraction = _extract_dns_record_entities(result)
    if extraction["entities"] or extraction["relationships"]:
        return extraction

    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = []
    source = _dns_source(result)
    for address in _extract_ip_candidates(result["output"]):
        entity = _build_entity(
            address,
            result["tool_name"],
            source,
            "resolves_to",
            fallback_type="ip",
        )
        if entity is None:
            continue
        entity["score"] = 0.9
        entity["classification"] = "resolved_ip"
        entities.append(entity)
        relationships.append(
            {
                "source": source,
                "target": entity["value"],
                "relationship": "resolves_to",
            }
        )
        events.append(f"Discovered IP {entity['value']} from {source}")
    return {"entities": entities, "relationships": relationships, "events": events}


def _extract_dns_soa_entities(result: ToolResult) -> ExtractionResult:
    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = []
    source = _dns_source(result)
    primary_nameserver: str | None = None
    record = _normalized_tool_payload(result).get("record")
    if isinstance(record, dict):
        candidate = record.get("primary_nameserver")
        if isinstance(candidate, str) and candidate.strip():
            primary_nameserver = candidate.strip().lower().rstrip(".")
    if primary_nameserver is None:
        for line in result["output"].splitlines():
            if line.startswith("- SOA: mname "):
                primary_nameserver = line.removeprefix("- SOA: mname ").strip().rstrip(".").lower()
                break
    if primary_nameserver:
        entity = _build_entity(
            primary_nameserver,
            result["tool_name"],
            source,
            "has_nameserver",
            fallback_type="nameserver",
        )
        if entity is not None and entity["value"] != source:
            entity["score"] = 0.15
            entity["classification"] = "nameserver"
            entities.append(entity)
            relationships.append(
                {
                    "source": source,
                    "target": entity["value"],
                    "relationship": "has_nameserver",
                }
            )
            events.append(f"Discovered nameserver {entity['value']} from {source}")
    return {
        "entities": entities,
        "relationships": relationships,
        "events": events,
    }


def _extract_dns_ns_entities(result: ToolResult) -> ExtractionResult:
    return _extract_dns_record_entities(result)


def _extract_reverse_dns_entities(result: ToolResult) -> ExtractionResult:
    return _extract_dns_record_entities(result)


def _extract_dns_entities(result: ToolResult) -> ExtractionResult:
    record_type = _dns_record_type(result)
    if record_type in {"A", "AAAA", "A+AAAA", "NS", "PTR"}:
        return _extract_dns_a_entities(result) if record_type in {"A", "AAAA", "A+AAAA"} else _extract_dns_record_entities(result)
    if record_type == "MX":
        return _extract_dns_mx_entities(result)
    if record_type == "SOA":
        return _extract_dns_soa_entities(result)

    tool_name = result["tool_name"]
    if tool_name == "dns_a_lookup":
        return _extract_dns_a_entities(result)
    if tool_name == "dns_mx_lookup":
        return _extract_dns_mx_entities(result)
    if tool_name == "dns_ns_lookup":
        return _extract_dns_ns_entities(result)
    if tool_name == "dns_soa_lookup":
        return _extract_dns_soa_entities(result)
    if tool_name == "reverse_dns_lookup":
        return _extract_reverse_dns_entities(result)
    return {"entities": [], "relationships": [], "events": []}


def _extract_tls_certificate_entities(result: ToolResult) -> ExtractionResult:
    normalized = _normalized_tool_payload(result)
    source = str(normalized.get("domain", result["input"])).lower()
    san_domains = normalized.get("san_domains", [])
    if not isinstance(san_domains, list):
        return {"entities": [], "relationships": [], "events": []}
    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = []
    seen_domains: set[str] = set()
    for san_domain in san_domains:
        if not isinstance(san_domain, str):
            continue
        candidate = san_domain.strip().lower().rstrip(".")
        if not candidate or candidate.startswith("*.") or candidate in seen_domains:
            continue
        seen_domains.add(candidate)
        entity = _build_entity(
            candidate,
            result["tool_name"],
            source,
            "certificate_contains",
            fallback_type="domain",
        )
        if entity is None or entity["value"] == source:
            continue
        entity["score"] = 0.5
        entity["classification"] = "tls_san"
        entities.append(entity)
        relationships.append(
            {
                "source": source,
                "target": entity["value"],
                "relationship": "certificate_contains",
            }
        )
        events.append(f"Discovered SAN domain {entity['value']} from {source}")
    return {"entities": entities, "relationships": relationships, "events": events}


def _extract_registration_entities(result: ToolResult) -> ExtractionResult:
    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = []
    normalized = _normalized_tool_payload(result)
    query_type = normalized.get("query_type")

    if query_type == "ip":
        ip_network = normalized.get("ip_network")
        if not isinstance(ip_network, dict):
            return {"entities": [], "relationships": [], "events": []}
        source_value = str(normalized.get("query", result["input"]))
        network = ip_network.get("network")
        if isinstance(network, str) and network.strip():
            network_entity = _build_entity(
                network,
                result["tool_name"],
                source_value,
                "belongs_to_network",
                fallback_type="network",
                status="pending",
            )
            if network_entity is not None:
                network_entity["score"] = 0.2
                network_entity["classification"] = "registration_network"
                entities.append(network_entity)
                relationships.append(
                    {
                        "source": source_value,
                        "target": network_entity["value"],
                        "relationship": "belongs_to_network",
                    }
                )
                events.append(f"Mapped network {network_entity['value']} from {source_value}")

                for field_name, relationship_name in (
                    ("country", "has_country"),
                    ("rir", "has_rir"),
                    ("name", "has_name"),
                ):
                    value = ip_network.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        continue
                    attribute = _build_entity(
                        value,
                        result["tool_name"],
                        network_entity["value"],
                        relationship_name,
                        fallback_type=field_name,
                        status="done",
                    )
                    if attribute is None:
                        continue
                    attribute["classification"] = "registration_attribute"
                    entities.append(attribute)
                    relationships.append(
                        {
                            "source": network_entity["value"],
                            "target": attribute["value"],
                            "relationship": relationship_name,
                        }
                    )

                for description in ip_network.get("description", []):
                    if not isinstance(description, str) or not description.strip():
                        continue
                    attribute = _build_entity(
                        description,
                        result["tool_name"],
                        network_entity["value"],
                        "has_description",
                        fallback_type="description",
                        status="done",
                    )
                    if attribute is None:
                        continue
                    attribute["classification"] = "registration_attribute"
                    entities.append(attribute)
                    relationships.append(
                        {
                            "source": network_entity["value"],
                            "target": attribute["value"],
                            "relationship": "has_description",
                        }
                    )

                for contact_key, relationship_name, queue_score in (
                    ("abuse_contacts", "has_abuse_contact", 0.55),
                    ("admin_contacts", "has_admin_contact", 0.15),
                    ("technical_contacts", "has_technical_contact", 0.15),
                    ("registrant_contacts", "has_registrant", 0.1),
                ):
                    contacts = ip_network.get(contact_key, [])
                    if not isinstance(contacts, list):
                        continue
                    for contact in contacts:
                        if not isinstance(contact, dict):
                            continue
                        email = contact.get("email")
                        if isinstance(email, str) and email.strip():
                            email_entity = _build_entity(
                                email,
                                result["tool_name"],
                                network_entity["value"],
                                relationship_name,
                                fallback_type="email",
                                status="pending" if relationship_name == "has_abuse_contact" else "done",
                            )
                            if email_entity is not None:
                                email_entity["score"] = queue_score
                                email_entity["classification"] = "registration_contact"
                                entities.append(email_entity)
                                relationships.append(
                                    {
                                        "source": network_entity["value"],
                                        "target": email_entity["value"],
                                        "relationship": relationship_name,
                                    }
                                )
                                events.append(
                                    f"Discovered registration contact {email_entity['value']} from {network_entity['value']}"
                                )

                        name = contact.get("name") or contact.get("handle")
                        if isinstance(name, str) and name.strip():
                            org_relationship = (
                                "has_abuse_org"
                                if relationship_name == "has_abuse_contact"
                                else relationship_name
                            )
                            name_entity = _build_entity(
                                name,
                                result["tool_name"],
                                network_entity["value"],
                                org_relationship,
                                fallback_type="organization",
                                status="done",
                            )
                            if name_entity is not None:
                                name_entity["classification"] = "registration_contact"
                                entities.append(name_entity)
                                relationships.append(
                                    {
                                        "source": network_entity["value"],
                                        "target": name_entity["value"],
                                        "relationship": org_relationship,
                                    }
                                )
    elif query_type == "domain":
        domain_registration = normalized.get("domain")
        if not isinstance(domain_registration, dict):
            return {"entities": [], "relationships": [], "events": []}
        source_value = str(normalized.get("query", result["input"]))
        for field_name, relationship_name, fallback_type, status, score in (
            ("registrar", "has_registrar", "organization", "done", None),
            ("registrar_abuse_email", "has_registrar_abuse_email", "email", "done", 0.15),
            ("registrant_email", "has_registrant_email", "email", "pending", 0.45),
            ("registrant_org", "has_registrant_org", "organization", "done", None),
        ):
            value = domain_registration.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue
            entity = _build_entity(
                value,
                result["tool_name"],
                source_value,
                relationship_name,
                fallback_type=fallback_type,
                status=status,
            )
            if entity is None:
                continue
            if score is not None:
                entity["score"] = score
            entity["classification"] = "registration_contact"
            entities.append(entity)
            relationships.append(
                {
                    "source": source_value,
                    "target": entity["value"],
                    "relationship": relationship_name,
                }
            )
        for nameserver in domain_registration.get("nameservers", []):
            if not isinstance(nameserver, str):
                continue
            entity = _build_entity(
                nameserver,
                result["tool_name"],
                source_value,
                "has_nameserver",
                fallback_type="nameserver",
                status="pending",
            )
            if entity is None or entity["value"] == source_value:
                continue
            entity["score"] = 0.15
            entity["classification"] = "nameserver"
            entities.append(entity)
            relationships.append(
                {
                    "source": source_value,
                    "target": entity["value"],
                    "relationship": "has_nameserver",
                }
            )
            events.append(f"Discovered nameserver {entity['value']} from {source_value}")
        for status_text in domain_registration.get("status", []):
            if not isinstance(status_text, str) or not status_text.strip():
                continue
            entity = _build_entity(
                status_text,
                result["tool_name"],
                source_value,
                "has_status",
                fallback_type="status",
                status="done",
            )
            if entity is None:
                continue
            entity["classification"] = "registration_attribute"
            entities.append(entity)
            relationships.append(
                {
                    "source": source_value,
                    "target": entity["value"],
                    "relationship": "has_status",
                }
            )

    return {
        "entities": entities,
        "relationships": relationships,
        "events": events,
    }


def _extract_entities_from_normalized_findings(result: ToolResult) -> ExtractionResult:
    findings = _normalized_finding_payload(result)
    raw_entities = findings.get("entities")
    raw_relationships = findings.get("relationships")
    raw_events = findings.get("events")
    if not isinstance(raw_entities, list):
        raw_entities = []
    if not isinstance(raw_relationships, list):
        raw_relationships = []
    if not isinstance(raw_events, list):
        raw_events = []

    entities: list[EntityRecord] = []
    relationships: list[RelationshipRecord] = []
    events: list[str] = [str(item).strip() for item in raw_events if str(item).strip()]

    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "")).strip()
        relationship = str(item.get("relationship", "related_to")).strip() or "related_to"
        parent = str(item.get("parent", result["input"])).strip() or result["input"]
        status = str(item.get("status", "pending")).strip() or "pending"
        fallback_type = str(item.get("type", "unknown")).strip() or "unknown"
        entity = _build_entity(
            value,
            result["tool_name"],
            parent,
            relationship,
            status=status,
            fallback_type=fallback_type,
        )
        if entity is None:
            continue
        score = item.get("score")
        classification = item.get("classification")
        if isinstance(score, (int, float)):
            entity["score"] = float(score)
        if isinstance(classification, str) and classification.strip():
            entity["classification"] = classification.strip()
        entities.append(entity)
        relationships.append(
            {
                "source": parent,
                "target": entity["value"],
                "relationship": relationship,
            }
        )

    for item in raw_relationships:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        relationship = str(item.get("relationship", "")).strip()
        if not source or not target or not relationship:
            continue
        relationships.append(
            {
                "source": source,
                "target": target,
                "relationship": relationship,
            }
        )

    deduped_relationships: list[RelationshipRecord] = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        key = _relationship_key(relationship)
        if key in seen_relationships:
            continue
        seen_relationships.add(key)
        deduped_relationships.append(relationship)

    return {
        "entities": entities,
        "relationships": deduped_relationships,
        "events": events,
    }


def _extract_entities_from_tool_result(result: ToolResult) -> ExtractionResult:
    if result["error"]:
        return {
            "entities": [],
            "relationships": [],
            "events": [],
        }
    if _uses_generic_normalized_findings(result):
        return _extract_entities_from_normalized_findings(result)
    if result["tool_name"] in {
        "dns_a_lookup",
        "dns_mx_lookup",
        "dns_ns_lookup",
        "dns_soa_lookup",
        "reverse_dns_lookup",
    }:
        return _extract_dns_entities(result)
    if result["tool_name"] == "registration_lookup":
        return _extract_registration_entities(result)
    if result["tool_name"] == "tls_certificate_lookup":
        return _extract_tls_certificate_entities(result)
    return {
        "entities": [],
        "relationships": [],
        "events": [],
    }


def _tool_event(result: ToolResult) -> str:
    if result.get("cached"):
        return result.get("cache_event", f"Cache hit for {result['tool_name']}({result['input']})")
    if result["error"]:
        return f"{_tool_label(result['tool_name']).capitalize()} failed for {result['input']}: {result['error']}"
    if result.get("planner_summary"):
        return result["planner_summary"].splitlines()[0]
    return f"Executed {result['tool_name']} with input {result['input']}"


def _planner_event(
    next_action: str,
    tool_input: str,
    reasoning_summary: str,
    stop_reason: str,
) -> str:
    if next_action == "report":
        detail = stop_reason or "planner selected report"
        return f"Planner selected report: {detail}"
    summary = reasoning_summary or "No reasoning summary provided."
    return f"Planner selected {next_action} for {tool_input}: {summary}"


def _tool_result_summary(result: ToolResult) -> str:
    source = " (from cache)" if result.get("cached") else ""
    if result["error"]:
        return (
            f"{_tool_label(result['tool_name']).capitalize()} failed for "
            f"`{result['input']}`{source}: {result['error']}"
        )
    planner_summary = result.get("planner_summary", "")
    if planner_summary:
        first_line, *rest = planner_summary.splitlines()
        summary = "; ".join(line.removeprefix("- ").strip() for line in rest[:3]) or first_line
        return f"{summary}{source}."
    return f"{_tool_label(result['tool_name']).capitalize()} completed for `{result['input']}`{source}."


def _registration_summaries(tool_results: list[ToolResult]) -> list[str]:
    lines: list[str] = []
    for result in tool_results:
        if result["tool_name"] != "registration_lookup":
            continue
        normalized = _normalized_tool_payload(result)
        if not normalized:
            if result["error"]:
                lines.append(f"`{result['input']}`: {result['error']}")
            elif result.get("planner_summary"):
                lines.append(result["planner_summary"])
            continue
        planner_summary = result.get("planner_summary", "")
        if planner_summary:
            lines.append(planner_summary.replace("\n", "; "))
    return lines


def _infrastructure_summaries(tool_results: list[ToolResult]) -> list[str]:
    lines: list[str] = []
    for result in tool_results:
        planner_summary = result.get("planner_summary", "")
        if planner_summary:
            lines.append(planner_summary.replace("\n", "; "))
    return lines


def _key_findings(state: GraphState) -> list[str]:
    findings: list[str] = []
    for result in state["tool_results"]:
        summary = _tool_result_summary(result)
        if summary not in findings:
            findings.append(summary)
    if state["pending_entities"]:
        findings.append(
            f"Discovered {len(state['pending_entities'])} additional entities worth future pivots."
        )
    if state["stop_reason"]:
        findings.append(f"Investigation stopped because {state['stop_reason']}.")
    return findings[:6]


def _raw_tool_output(tool_results: list[ToolResult]) -> str:
    if not tool_results:
        return "_No tool output collected._"

    sections: list[str] = []
    for result in tool_results:
        if result["tool_name"] in {
            "registration_lookup",
            "dns_ns_lookup",
            "reverse_dns_lookup",
            "dns_txt_lookup",
            "tls_certificate_lookup",
        } and result.get("planner_summary"):
            body = "\n".join(
                [
                    result["planner_summary"],
                    "",
                    "Normalized pivot summary shown here. Full structured payload is preserved in state.json.",
                ]
            )
        else:
            body = result["output"] or result["error"] or "(empty)"
        sections.append(
            "\n".join(
                [
                    f"### {result['tool_name']} `{result['input']}`",
                    f"_cached: {result.get('cached', False)}_",
                    "```text",
                    body,
                    "```",
                ]
            )
        )
    return "\n\n".join(sections)


def _format_bullets(items: list[str], empty_message: str) -> str:
    if not items:
        return f"- {empty_message}"
    return "\n".join(f"- {item}" for item in items)


def _report_summary(state: GraphState) -> str:
    findings = _key_findings(state)
    if findings:
        return findings[0]
    return f"Investigation completed for `{state['entity']}`."


def _tool_already_used(tool_results: list[ToolResult], tool_name: str, input: str) -> bool:
    return any(
        result["tool_name"] == tool_name and result["input"] == input for result in tool_results
    )


def _discovered_ip_candidates(tool_results: list[ToolResult]) -> list[str]:
    candidates: list[str] = []
    for result in tool_results:
        for source in (result["input"], result["output"], result["error"]):
            if not source:
                continue
            for candidate in _extract_ip_candidates(source):
                if candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def _first_unused_candidate(
    tool_results: list[ToolResult],
    tool_name: str,
    candidates: list[str],
) -> str:
    for candidate in candidates:
        if not _tool_already_used(tool_results, tool_name, candidate):
            return candidate
    return ""


def _tool_supports_entity(tool_name: str, entity_type: str) -> bool:
    if tool_name == "dns_a_lookup":
        return entity_type in {"domain", "url", "hostname", "nameserver"}
    if tool_name == "dns_mx_lookup":
        return entity_type in {"domain", "url", "hostname"}
    if tool_name == "dns_ns_lookup":
        return entity_type in {"domain", "url", "hostname"}
    if tool_name == "dns_soa_lookup":
        return entity_type in {"domain", "url", "hostname"}
    if tool_name == "dns_txt_lookup":
        return entity_type in {"domain", "url", "hostname"}
    if tool_name == "tls_certificate_lookup":
        return entity_type in {"domain", "hostname"}
    if tool_name == "reverse_dns_lookup":
        return entity_type == "ip"
    if tool_name == "registration_lookup":
        return entity_type in {"domain", "url", "ip"}
    return True


def _pending_investigation_selection(
    state: GraphState,
    enabled_tool_names: list[str],
) -> tuple[str, str]:
    pending_entities = sorted(
        state["pending_entities"],
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )
    for entity in pending_entities:
        tool_priority: list[str]
        if entity["type"] == "ip":
            tool_priority = ["registration_lookup", "reverse_dns_lookup"]
        elif entity["type"] == "domain":
            tool_priority = [
                "dns_a_lookup",
                "registration_lookup",
                "tls_certificate_lookup",
                "dns_ns_lookup",
                "dns_mx_lookup",
                "dns_soa_lookup",
                "dns_txt_lookup",
            ]
        elif entity["type"] == "hostname":
            tool_priority = [
                "dns_a_lookup",
                "tls_certificate_lookup",
                "registration_lookup",
            ]
        elif entity["type"] == "nameserver":
            tool_priority = ["dns_a_lookup"]
        else:
            tool_priority = []

        for tool_name in tool_priority:
            if tool_name not in enabled_tool_names:
                continue
            if not _tool_supports_entity(tool_name, entity["type"]):
                continue
            if not _tool_already_used(state["tool_results"], tool_name, entity["value"]):
                return tool_name, entity["value"]

    return "", ""


def _fallback_tool_selection(
    state: GraphState,
    enabled_tool_names: list[str],
) -> tuple[str, str]:
    pending_action, pending_input = _pending_investigation_selection(state, enabled_tool_names)
    if pending_action:
        return pending_action, pending_input

    discovered_ips = _discovered_ip_candidates(state["tool_results"])
    for tool_name in enabled_tool_names:
        if not _tool_supports_entity(tool_name, state["entity_type"]):
            continue
        if tool_name == "dns_a_lookup":
            if state["entity_type"] in {"domain", "url", "hostname", "nameserver"}:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"]],
                )
                if tool_input:
                    return tool_name, tool_input
        elif tool_name == "dns_ns_lookup":
            if state["entity_type"] in {"domain", "url", "hostname"}:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"]],
                )
                if tool_input:
                    return tool_name, tool_input
        elif tool_name == "tls_certificate_lookup":
            if state["entity_type"] in {"domain", "hostname"}:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"]],
                )
                if tool_input:
                    return tool_name, tool_input
        elif tool_name == "reverse_dns_lookup":
            if state["entity_type"] == "ip":
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"], *discovered_ips],
                )
                if tool_input:
                    return tool_name, tool_input
        elif tool_name == "registration_lookup":
            if state["entity_type"] == "ip":
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"], *discovered_ips],
                )
                if tool_input:
                    return tool_name, tool_input
            if discovered_ips:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    discovered_ips,
                )
                if tool_input:
                    return tool_name, tool_input
            if state["entity_type"] in {"domain", "url"}:
                tool_input = _first_unused_candidate(
                    state["tool_results"],
                    tool_name,
                    [state["entity"], state["raw_input"]],
                )
                if tool_input:
                    return tool_name, tool_input

    for tool_name in enabled_tool_names:
        if not _tool_supports_entity(tool_name, state["entity_type"]):
            continue
        tool_input = _first_unused_candidate(
            state["tool_results"],
            tool_name,
            [state["entity"], state["raw_input"], *discovered_ips],
        )
        if tool_input:
            return tool_name, tool_input

    return "report", ""


def _skill_prompt(skill: Skill | None) -> str:
    if skill is None:
        return ""
    return (
        f"Selected skill: {skill.name}\n"
        f"Skill description: {skill.description}\n"
        "Skill markdown:\n"
        f"{skill.body}"
    )


def _build_seed_entity(value: str, entity_type: str, raw_input: str) -> EntityRecord:
    canonical, canonical_type = _canonicalize_entity(value, fallback_type=entity_type)
    return {
        "value": canonical,
        "type": canonical_type,
        "source_tool": "normalize_entity",
        "parent": raw_input,
        "status": "investigating",
        "relationship": "seed",
    }


def _analyze_latest_tool_result(state: GraphState) -> tuple[
    list[EntityRecord],
    list[EntityRecord],
    list[str],
    list[RelationshipRecord],
    list[str],
]:
    discovered_entities = [dict(entity) for entity in state["discovered_entities"]]
    relationships = list(state["relationships"])
    events: list[str] = []

    if not state["tool_results"]:
        pending_entities, investigated_entities = _sync_investigation_views(discovered_entities)
        return discovered_entities, pending_entities, investigated_entities, relationships, events

    latest_result = state["tool_results"][-1]
    investigated_input, investigated_type = _canonicalize_entity(
        latest_result["input"],
        fallback_type=state["entity_type"],
    )
    discovered_entities, _ = _set_entity_status(
        discovered_entities,
        investigated_input,
        "done",
        source_tool=latest_result["tool_name"],
        fallback_type=investigated_type,
    )

    extraction = _extract_entities_from_tool_result(latest_result)
    for entity in extraction["entities"]:
        discovered_entities, created = _merge_entity(discovered_entities, entity)
        if created:
            merged_entity = next(
                (
                    existing
                    for existing in discovered_entities
                    if existing["value"] == entity["value"] and existing["type"] == entity["type"]
                ),
                None,
            )
            if merged_entity is not None and is_queueable_entity(merged_entity):
                events = _append_event(events, f"Queued entity {merged_entity['value']} for investigation")

            parent_domain_pivot = _build_parent_domain_pivot(entity)
            if parent_domain_pivot is not None:
                parent_entity, parent_relationship, parent_event = parent_domain_pivot
                discovered_entities, parent_created = _merge_entity(discovered_entities, parent_entity)
                if parent_created:
                    merged_parent = next(
                        (
                            existing
                            for existing in discovered_entities
                            if existing["value"] == parent_entity["value"] and existing["type"] == parent_entity["type"]
                        ),
                        None,
                    )
                    if merged_parent is not None and is_queueable_entity(merged_parent):
                        events = _append_event(events, f"Queued entity {merged_parent['value']} for investigation")
                relationships, parent_relationship_created = _merge_relationship(relationships, parent_relationship)
                if parent_relationship_created:
                    events = _append_event(
                        events,
                        "Mapped relationship "
                        f"{parent_relationship['source']} -> {parent_relationship['relationship']} -> {parent_relationship['target']}",
                    )
                if parent_created or parent_relationship_created:
                    events = _append_event(events, parent_event)

    for relationship in extraction["relationships"]:
        relationships, created = _merge_relationship(relationships, relationship)
        if created:
            events = _append_event(
                events,
                "Mapped relationship "
                f"{relationship['source']} -> {relationship['relationship']} -> {relationship['target']}",
            )

    for event in extraction["events"]:
        events = _append_event(events, event)

    pending_entities, investigated_entities = _sync_investigation_views(discovered_entities)
    return discovered_entities, pending_entities, investigated_entities, relationships, events


def _group_discovered_entities(state: GraphState) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "Domains": [],
        "Hostnames": [],
        "Nameservers": [],
        "IPs": [],
        "Emails": [],
        "ASNs": [],
    }
    nameserver_targets = {
        relationship["target"]
        for relationship in state["relationships"]
        if relationship["relationship"] == "has_nameserver"
    }
    for entity in state["discovered_entities"]:
        value = entity["value"]
        if value in nameserver_targets and value not in groups["Nameservers"]:
            groups["Nameservers"].append(value)
        if entity["type"] == "domain" and value not in nameserver_targets:
            if value not in groups["Domains"]:
                groups["Domains"].append(value)
        elif entity["type"] == "hostname" and value not in groups["Hostnames"]:
            groups["Hostnames"].append(value)
        elif entity["type"] == "nameserver" and value not in groups["Nameservers"]:
            groups["Nameservers"].append(value)
        elif entity["type"] == "ip" and value not in groups["IPs"]:
            groups["IPs"].append(value)
        elif entity["type"] == "email" and value not in groups["Emails"]:
            groups["Emails"].append(value)
        elif entity["type"] == "asn" and value not in groups["ASNs"]:
            groups["ASNs"].append(value)
    return groups


def _format_discovered_entities_section(state: GraphState) -> str:
    groups = _group_discovered_entities(state)
    sections: list[str] = []
    for heading, values in groups.items():
        sections.append(f"### {heading}\n")
        if values:
            sections.append("\n".join(f"- {value}" for value in values))
        else:
            sections.append("- None")
        sections.append("")
    return "\n".join(sections).strip()


def _format_relationships_section(state: GraphState) -> str:
    if not state["relationships"]:
        return "- No relationships discovered."

    grouped: dict[str, list[RelationshipRecord]] = {}
    for relationship in state["relationships"]:
        grouped.setdefault(relationship["source"], []).append(relationship)

    lines: list[str] = []
    for source, relationships in grouped.items():
        lines.append(source)
        last_index = len(relationships) - 1
        for index, relationship in enumerate(relationships):
            branch = "└─" if index == last_index else "├─"
            lines.append(
                f"  {branch} {relationship['relationship']} -> {relationship['target']}"
            )
        lines.append("")
    return "\n".join(lines).strip()


def build_graph(config: ArgusConfig, skill: Skill | None = None):
    client, model, temperature = _make_client(config)
    tool_registry = build_tool_registry(config)
    max_steps = config["agent"]["max_steps"]
    enabled_tool_names = tool_registry.available_tool_names()
    enabled_tool_descriptions = tool_registry.available_tool_descriptions()
    skill_name = skill.name if skill is not None else "none"
    skill_context = _skill_prompt(skill)

    def normalize_entity(state: GraphState) -> GraphState:
        normalized = normalize_entity_tool(state["raw_input"])
        seed_entity = _build_seed_entity(
            normalized["entity"],
            normalized["entity_type"],
            normalized["raw_input"],
        )
        pending_entities, investigated_entities = _sync_investigation_views([seed_entity])
        return {
            "raw_input": normalized["raw_input"],
            "entity": normalized["entity"],
            "entity_type": normalized["entity_type"],
            "run_started_at": state["run_started_at"],
            "events": [
                f"Started investigation of {normalized['entity']}",
                f"Normalized input as {normalized['entity']} ({normalized['entity_type']})",
            ],
            "reasoning_summary": "",
            "next_action": "",
            "tool_input": "",
            "stop_reason": "",
            "skill_name": skill_name,
            "tool_results": [],
            "steps_remaining": max_steps,
            "discovered_entities": [seed_entity],
            "pending_entities": pending_entities,
            "investigated_entities": investigated_entities,
            "relationships": [],
            "snapshots": [],
            "report": "",
        }

    def planner(state: GraphState) -> GraphState:
        enabled_tool_prompt = "\n".join(
            f"- {tool_name}: {description}" for tool_name, description in enabled_tool_descriptions
        )
        fallback_action, fallback_tool_input = _fallback_tool_selection(
            state,
            enabled_tool_names,
        )
        fallback_reason = "no remaining enabled tools."
        if fallback_action != "report":
            fallback_reason = ""
        fallback_notes = f"Planner unavailable for `{state['entity']}`."
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a concise investigation planner. "
                            "Return JSON only with keys reasoning_summary, next_action, "
                            "tool_input, and stop_reason. "
                            "reasoning_summary must explain why the next action was selected "
                            "without repeating the full investigation history.\n"
                            "next_action must be exactly one enabled tool name or report.\n"
                            "If next_action is a tool, tool_input must be a string to pass "
                            "to that tool.\n"
                            "If next_action is report, tool_input may be empty and stop_reason "
                            "must be populated.\n"
                            "If next_action is a tool, stop_reason must be empty.\n"
                            "Prefer investigating meaningful pending entities before collecting "
                            "additional low-value information.\n"
                            "Focus on pivots. Newly discovered domains, nameservers, IPs, and "
                            "other infrastructure are often more valuable than collecting every "
                            "possible DNS record type.\n"
                            "For domains and hostnames, prefer dns_a_lookup, registration_lookup, "
                            "dns_ns_lookup, and tls_certificate_lookup when they can expose new pivots.\n"
                            "For IPs, prefer registration_lookup and reverse_dns_lookup.\n"
                            "Do not use TLS certificate lookup for IPs.\n"
                            "Do not use reverse DNS lookup for domains.\n"
                            f"{skill_context}\n"
                            "Enabled tools:\n"
                            f"{enabled_tool_prompt or '- None'}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Raw input: `{state['raw_input']}`\n"
                            f"Normalized entity: `{state['entity']}`\n"
                            f"Entity type: `{state['entity_type']}`\n"
                            f"Steps remaining: {state['steps_remaining']}\n"
                            f"Selected skill: `{state['skill_name']}`\n"
                            "Investigation timeline:\n"
                            f"{_format_bullets(state['events'], 'No events recorded yet.')}\n"
                            "Discovered entities:\n"
                            f"{_format_entities_for_prompt(state['discovered_entities'], 'None')}\n"
                            "Pending entities:\n"
                            f"{_format_entities_for_prompt(state['pending_entities'], 'None')}\n"
                            "Investigated entities:\n"
                            f"{_format_bullets(state['investigated_entities'], 'None')}\n"
                            "Relationships:\n"
                            f"{_format_relationships_for_prompt(state['relationships'], 'None')}\n"
                            "Enabled tools:\n"
                            f"{enabled_tool_prompt or '- None'}\n"
                            "Previous tool results:\n"
                            f"{_format_tool_results(state['tool_results'])}\n"
                            "Return JSON only with keys reasoning_summary, next_action, "
                            "tool_input, and stop_reason."
                        ),
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            parsed = json.loads(content)
            reasoning_summary = parsed.get("reasoning_summary", "")
            next_action = parsed.get("next_action", "")
            tool_input = parsed.get("tool_input", "")
            stop_reason = parsed.get("stop_reason", "")
            if next_action not in {*enabled_tool_names, "report"}:
                raise ValueError("next_action must be an enabled tool name or report.")
            if not isinstance(reasoning_summary, str):
                raise ValueError("reasoning_summary must be a string.")
            reasoning_summary = reasoning_summary.strip()
            if next_action != "report":
                if not isinstance(tool_input, str) or not tool_input.strip():
                    raise ValueError("tool_input must be provided for tool actions.")
                tool_input = tool_input.strip()
                stop_reason = ""
            else:
                tool_input = ""
                if not isinstance(stop_reason, str) or not stop_reason.strip():
                    raise ValueError("stop_reason must be provided for report actions.")
                stop_reason = stop_reason.strip()
        except Exception as exc:
            events = list(state["events"])
            if isinstance(exc, json.JSONDecodeError):
                reasoning_summary = "Planner output could not be parsed."
                next_action = "report"
                tool_input = ""
                stop_reason = f"planner output could not be parsed: {exc}"
            else:
                reasoning_summary = f"Planner call failed, using fallback selection. {exc}"
                next_action = fallback_action
                tool_input = fallback_tool_input
                stop_reason = fallback_reason if fallback_action == "report" else ""
                events = _append_event(events, f"{fallback_notes} {exc}")
        else:
            events = list(state["events"])
        snapshots = list(state["snapshots"])
        snapshots.append(
            _build_snapshot(state, next_action, tool_input, reasoning_summary, stop_reason)
        )
        events = _append_event(
            events,
            _planner_event(next_action, tool_input, reasoning_summary, stop_reason),
        )
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "run_started_at": state["run_started_at"],
            "events": events,
            "reasoning_summary": reasoning_summary,
            "next_action": next_action,
            "tool_input": tool_input,
            "stop_reason": stop_reason,
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "discovered_entities": state["discovered_entities"],
            "pending_entities": state["pending_entities"],
            "investigated_entities": state["investigated_entities"],
            "relationships": state["relationships"],
            "snapshots": snapshots,
            "report": "",
        }

    def route(state: GraphState) -> GraphState:
        events = list(state["events"])
        next_action = state["next_action"]
        tool_input = state["tool_input"]
        stop_reason = state["stop_reason"]
        discovered_entities = [dict(entity) for entity in state["discovered_entities"]]

        if next_action != "report" and state["steps_remaining"] <= 0:
            stop_reason = "max steps reached."
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and not tool_registry.has(next_action):
            stop_reason = f"disabled or missing tool `{next_action}`."
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and not isinstance(tool_input, str):
            stop_reason = "missing tool input."
            next_action = "report"
            tool_input = ""
        elif next_action != "report" and not tool_input.strip():
            stop_reason = "missing tool input."
            next_action = "report"
            tool_input = ""
        else:
            _, tool_input_type = _canonicalize_entity(tool_input, fallback_type=state["entity_type"])
            if next_action != "report" and not _tool_supports_entity(next_action, tool_input_type):
                stop_reason = f"`{next_action}` does not support entity type `{tool_input_type}`."
                next_action = "report"
                tool_input = ""
            elif next_action != "report" and _tool_already_used(
                state["tool_results"],
                next_action,
                tool_input,
            ):
                stop_reason = f"duplicate tool/input pair `{next_action}` / `{tool_input}`."
                next_action = "report"
                tool_input = ""
            elif next_action != "report":
                discovered_entities, changed = _set_entity_status(
                    discovered_entities,
                    tool_input,
                    "investigating",
                    source_tool="planner",
                    parent=state["entity"],
                    relationship="investigates",
                    fallback_type=tool_input_type,
                )
                if changed:
                    events = _append_event(events, f"Started investigating {tool_input}")

        if next_action == "report":
            stop_reason = stop_reason or "planner selected report."
            last_event = events[-1] if events else ""
            expected = f"Planner selected report: {stop_reason}"
            if last_event != expected:
                events = _append_event(events, f"Stopped investigation: {stop_reason}")

        pending_entities, investigated_entities = _sync_investigation_views(discovered_entities)
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "run_started_at": state["run_started_at"],
            "events": events,
            "reasoning_summary": state["reasoning_summary"],
            "next_action": next_action,
            "tool_input": tool_input,
            "stop_reason": stop_reason,
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "discovered_entities": discovered_entities,
            "pending_entities": pending_entities,
            "investigated_entities": investigated_entities,
            "relationships": state["relationships"],
            "snapshots": state["snapshots"],
            "report": state["report"],
        }

    def tool_executor(state: GraphState) -> GraphState:
        result = tool_registry.run(state["next_action"], state["tool_input"])
        tool_results = list(state["tool_results"])
        tool_results.append(result)
        events = list(state["events"])
        cache_error = result.get("cache_error", "")
        if cache_error:
            events = _append_event(events, cache_error)
        cache_event = result.get("cache_event", "")
        if cache_event and not result.get("cached"):
            events = _append_event(events, cache_event)
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "run_started_at": state["run_started_at"],
            "events": _append_event(events, _tool_event(result)),
            "reasoning_summary": state["reasoning_summary"],
            "next_action": state["next_action"],
            "tool_input": state["tool_input"],
            "stop_reason": "",
            "skill_name": state["skill_name"],
            "tool_results": tool_results,
            "steps_remaining": max(state["steps_remaining"] - 1, 0),
            "discovered_entities": state["discovered_entities"],
            "pending_entities": state["pending_entities"],
            "investigated_entities": state["investigated_entities"],
            "relationships": state["relationships"],
            "snapshots": state["snapshots"],
            "report": "",
        }

    def analyze_result(state: GraphState) -> GraphState:
        discovered_entities, pending_entities, investigated_entities, relationships, new_events = (
            _analyze_latest_tool_result(state)
        )
        events = list(state["events"])
        for event in new_events:
            events = _append_event(events, event)
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "run_started_at": state["run_started_at"],
            "events": events,
            "reasoning_summary": state["reasoning_summary"],
            "next_action": state["next_action"],
            "tool_input": state["tool_input"],
            "stop_reason": state["stop_reason"],
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "discovered_entities": discovered_entities,
            "pending_entities": pending_entities,
            "investigated_entities": investigated_entities,
            "relationships": relationships,
            "snapshots": state["snapshots"],
            "report": "",
        }

    def report(state: GraphState) -> GraphState:
        summary = _report_summary(state)
        key_findings = _format_bullets(_key_findings(state), "No significant findings recorded.")
        registration = _format_bullets(
            _registration_summaries(state["tool_results"]),
            "No registration information collected.",
        )
        infrastructure = _format_bullets(
            _infrastructure_summaries(state["tool_results"]),
            "No infrastructure information collected.",
        )
        discovered_entities = _format_discovered_entities_section(state)
        relationships = _format_relationships_section(state)
        timeline = _format_bullets(state["events"], "No investigation events recorded.")
        evidence = _format_bullets(
            [_tool_result_summary(result) for result in state["tool_results"]],
            "No evidence collected.",
        )
        markdown_report = (
            "# Investigation Report\n\n"
            "## Summary\n\n"
            f"{summary}\n\n"
            "## Key Findings\n\n"
            f"{key_findings}\n\n"
            "## Registration Information\n\n"
            f"{registration}\n\n"
            "## Infrastructure\n\n"
            f"{infrastructure}\n\n"
            "## Discovered Entities\n\n"
            f"{discovered_entities}\n\n"
            "## Relationships\n\n"
            "```text\n"
            f"{relationships}\n"
            "```\n\n"
            "## Investigation Timeline\n\n"
            f"{timeline}\n\n"
            "## Evidence\n\n"
            f"{evidence}\n\n"
            "## Raw Tool Output\n\n"
            f"{_raw_tool_output(state['tool_results'])}"
        )
        return {
            "raw_input": state["raw_input"],
            "entity": state["entity"],
            "entity_type": state["entity_type"],
            "run_started_at": state["run_started_at"],
            "events": state["events"],
            "reasoning_summary": state["reasoning_summary"],
            "next_action": state["next_action"],
            "tool_input": state["tool_input"],
            "stop_reason": state["stop_reason"],
            "skill_name": state["skill_name"],
            "tool_results": state["tool_results"],
            "steps_remaining": state["steps_remaining"],
            "discovered_entities": state["discovered_entities"],
            "pending_entities": state["pending_entities"],
            "investigated_entities": state["investigated_entities"],
            "relationships": state["relationships"],
            "snapshots": state["snapshots"],
            "report": markdown_report,
        }

    graph = StateGraph(GraphState)
    graph.add_node("start", lambda state: start(state, max_steps, skill_name))
    graph.add_node("normalize_entity", normalize_entity)
    graph.add_node("planner", planner)
    graph.add_node("route", route)
    graph.add_node("tool_executor", tool_executor)
    graph.add_node("analyze_result", analyze_result)
    graph.add_node("report", report)
    graph.add_edge(START, "start")
    graph.add_edge("start", "normalize_entity")
    graph.add_edge("normalize_entity", "planner")
    graph.add_edge("planner", "route")
    graph.add_conditional_edges(
        "route",
        lambda state: "tool_executor" if state["next_action"] != "report" else "report",
        {
            "tool_executor": "tool_executor",
            "report": "report",
        },
    )
    graph.add_edge("tool_executor", "analyze_result")
    graph.add_edge("analyze_result", "planner")
    graph.add_edge("report", END)
    return graph.compile()


__all__ = [
    "EntityRecord",
    "ExtractionResult",
    "GraphState",
    "RelationshipRecord",
    "_analyze_latest_tool_result",
    "_extract_dns_a_entities",
    "_extract_dns_mx_entities",
    "_extract_dns_soa_entities",
    "_extract_registration_entities",
    "_extract_entities_from_tool_result",
    "build_graph",
    "entity_type_is_queueable",
]

"""Registration and ownership lookup tools for Argus."""

from __future__ import annotations

import ipaddress
import json
from typing import Any, Literal
from urllib.parse import urlparse

import whois
import whoisit

from argus.tools.base import StructuredToolOutput, Tool
from argus.tools.whois.models import NormalizedRegistrationResult
from argus.tools.whois.normalize import (
    _is_nonempty,
    normalize_domain_registration_result,
    normalize_ip_rdap_result,
)


def _normalize_target(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.hostname:
            return parsed.hostname.lower(), "url"
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return candidate.lower(), "domain"
    return candidate, "ip"


def _sanitize_whois_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(result)
    sanitized.pop("raw", None)
    return sanitized


def _registration_planner_summary(normalized: NormalizedRegistrationResult) -> str:
    lines = [f"Registration lookup for {normalized.query}:"]
    if normalized.query_type == "ip" and normalized.ip_network is not None:
        ip_data = normalized.ip_network
        if ip_data.network:
            lines.append(f"- Network: {ip_data.network}")
        if ip_data.name:
            lines.append(f"- Name: {ip_data.name}")
        if ip_data.country:
            lines.append(f"- Country: {ip_data.country}")
        if ip_data.rir:
            lines.append(f"- RIR: {ip_data.rir}")
        for description in ip_data.description:
            lines.append(f"- Description: {description}")
        for contact in ip_data.abuse_contacts[:1]:
            if contact.name and contact.email:
                lines.append(f"- Abuse contact: {contact.name} <{contact.email}>")
            elif contact.email:
                lines.append(f"- Abuse contact: {contact.email}")
        for label, contacts in (
            ("Admin contact", ip_data.admin_contacts),
            ("Technical contact", ip_data.technical_contacts),
        ):
            for contact in contacts[:1]:
                if contact.name:
                    lines.append(f"- {label}: {contact.name}")
                elif contact.email:
                    lines.append(f"- {label}: {contact.email}")
    elif normalized.query_type == "domain" and normalized.domain is not None:
        domain_data = normalized.domain
        if domain_data.registrar:
            lines.append(f"- Registrar: {domain_data.registrar}")
        if domain_data.registrant_org:
            lines.append(f"- Registrant org: {domain_data.registrant_org}")
        if domain_data.registrant_email:
            lines.append(f"- Registrant email: {domain_data.registrant_email}")
        for nameserver in domain_data.nameservers[:3]:
            lines.append(f"- Nameserver: {nameserver}")
        for status in domain_data.status[:3]:
            lines.append(f"- Status: {status}")
    return "\n".join(lines)


def _structured_registration_output(
    query: str,
    query_type: Literal["domain", "ip"],
    source: Literal["whois", "rdap"],
    normalized: NormalizedRegistrationResult,
    raw: dict[str, Any] | str,
) -> StructuredToolOutput:
    output = (
        f"{source.upper()} normalized:\n"
        f"{json.dumps(normalized.model_dump(mode='json'), indent=2, sort_keys=True)}"
    )
    return {
        "output": output,
        "normalized": normalized.model_dump(mode="json"),
        "raw": {
            "query": query,
            "query_type": query_type,
            "source": source,
            "response": raw,
        },
        "planner_summary": _registration_planner_summary(normalized),
    }


def _whois_lookup(domain: str) -> tuple[dict[str, Any] | None, str]:
    try:
        result = whois.whois(
            domain,
            command=False,
            quiet=True,
            ignore_socket_errors=True,
            timeout=10,
        )
        if not isinstance(result, dict):
            return None, f"- WHOIS lookup for `{domain}` returned an unexpected result."
        sanitized = _sanitize_whois_result(result)
        if not _is_nonempty(sanitized):
            return None, f"- WHOIS lookup for `{domain}` returned no usable fields."
        return sanitized, ""
    except Exception as exc:  # pragma: no cover - network/runtime-specific
        return None, f"- WHOIS lookup failed for `{domain}`: {exc}"


def _ensure_rdap_bootstrapped() -> str:
    if whoisit.is_bootstrapped():
        return ""
    try:
        whoisit.bootstrap()
        return ""
    except Exception as exc:  # pragma: no cover - network/runtime-specific
        return f"- RDAP bootstrap failed: {exc}"


def _rdap_lookup(target: str, entity_type: str) -> tuple[dict[str, Any] | None, str]:
    bootstrap_error = _ensure_rdap_bootstrapped()
    if bootstrap_error:
        return None, bootstrap_error
    try:
        if entity_type == "ip":
            result = whoisit.ip(target)
        else:
            result = whoisit.domain(target)
        if not isinstance(result, dict):
            return None, f"- RDAP lookup for `{target}` returned an unexpected result."
        if not _is_nonempty(result):
            return None, f"- RDAP lookup for `{target}` returned no usable fields."
        return result, ""
    except Exception as exc:  # pragma: no cover - network/runtime-specific
        return None, f"- RDAP lookup failed for `{target}`: {exc}"


def _registration_lookup(value: str) -> StructuredToolOutput | str:
    target, entity_type = _normalize_target(value)
    query_type: Literal["domain", "ip"] = "ip" if entity_type == "ip" else "domain"

    if entity_type == "ip":
        rdap_result, rdap_error = _rdap_lookup(target, entity_type)
        if rdap_result is not None:
            normalized = normalize_ip_rdap_result(target, rdap_result)
            return _structured_registration_output(
                target, query_type, "rdap", normalized, rdap_result
            )
        return rdap_error

    whois_result, whois_error = _whois_lookup(target)
    if whois_result is not None:
        normalized = normalize_domain_registration_result(target, whois_result, "whois")
        return _structured_registration_output(
            target, query_type, "whois", normalized, whois_result
        )

    rdap_result, rdap_error = _rdap_lookup(target, entity_type)
    if rdap_result is not None:
        normalized = normalize_domain_registration_result(target, rdap_result, "rdap")
        return _structured_registration_output(
            target, query_type, "rdap", normalized, rdap_result
        )

    fallback_note = whois_error or f"- WHOIS lookup for `{target}` was unavailable."
    return "\n".join([fallback_note, rdap_error])


registration_lookup = Tool(
    name="registration_lookup",
    description="Look up registration and ownership information for domains and IPs.",
    runner=_registration_lookup,
)

__all__ = [
    "registration_lookup",
]

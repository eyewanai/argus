"""Registration and ownership lookup tools for Argus."""

from __future__ import annotations

import ipaddress
import json
from typing import Any
from urllib.parse import urlparse

import whois
import whoisit

from argus.tools.base import Tool


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


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_is_nonempty(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_is_nonempty(item) for item in value)
    return True


def _sanitize_whois_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(result)
    sanitized.pop("raw", None)
    return sanitized


def _format_json_block(title: str, data: Any) -> str:
    return f"{title}:\n{json.dumps(data, indent=2, sort_keys=True, default=str)}"


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


def _registration_lookup(value: str) -> str:
    target, entity_type = _normalize_target(value)
    if entity_type == "ip":
        rdap_result, rdap_error = _rdap_lookup(target, entity_type)
        if rdap_result is not None:
            return _format_json_block("RDAP", rdap_result)
        return rdap_error

    whois_result, whois_error = _whois_lookup(target)
    if whois_result is not None:
        return _format_json_block("WHOIS", whois_result)

    rdap_result, rdap_error = _rdap_lookup(target, entity_type)
    if rdap_result is not None:
        fallback_note = whois_error or f"- WHOIS lookup for `{target}` was unavailable."
        return "\n".join([fallback_note, _format_json_block("RDAP", rdap_result)])

    fallback_note = whois_error or f"- WHOIS lookup for `{target}` was unavailable."
    return "\n".join([fallback_note, rdap_error])


registration_lookup = Tool(
    name="registration_lookup",
    description="Look up registration and ownership information for domains and IPs.",
    runner=_registration_lookup,
)

__all__ = ["registration_lookup"]

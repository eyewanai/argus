"""Entity normalization helpers for Argus."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def normalize_entity(input: str) -> dict[str, str]:
    raw_input = input
    value = input.strip()

    if not value:
        return {
            "raw_input": raw_input,
            "entity": "",
            "entity_type": "unknown",
        }

    if "://" in value:
        parsed = urlparse(value)
        hostname = parsed.hostname or ""
        if hostname:
            return {
                "raw_input": raw_input,
                "entity": hostname,
                "entity_type": "url",
            }

    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return {
            "raw_input": raw_input,
            "entity": value,
            "entity_type": "ip",
        }

    if _looks_like_domain(value):
        return {
            "raw_input": raw_input,
            "entity": value,
            "entity_type": "domain",
        }

    return {
        "raw_input": raw_input,
        "entity": value,
        "entity_type": "unknown",
    }


def _looks_like_domain(value: str) -> bool:
    if " " in value or "/" in value:
        return False
    if value.endswith("."):
        value = value[:-1]
    labels = value.split(".")
    if len(labels) < 2:
        return False
    for label in labels:
        if not label:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
    return True

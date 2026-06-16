"""TLS certificate lookup tool for Argus."""

from __future__ import annotations

import json
import socket
import ssl
from datetime import UTC, datetime

from argus.tools.base import StructuredToolOutput, Tool
from argus.tools.tls.models import TLSCertificateResult


def _parse_cert_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    except ValueError:
        return None


def _flatten_name(parts: tuple[tuple[tuple[str, str], ...], ...] | tuple) -> str | None:
    flattened: list[str] = []
    for group in parts:
        if not isinstance(group, tuple):
            continue
        for item in group:
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            key, value = item
            flattened.append(f"{key}={value}")
    return ", ".join(flattened) if flattened else None


def _normalized_tls_output(domain: str, cert: dict) -> StructuredToolOutput:
    san_domains: list[str] = []
    for name_type, value in cert.get("subjectAltName", []):
        if name_type != "DNS":
            continue
        candidate = value.strip().lower().rstrip(".")
        if candidate.startswith("*."):
            continue
        if candidate and candidate not in san_domains:
            san_domains.append(candidate)

    normalized = TLSCertificateResult(
        domain=domain,
        subject=_flatten_name(cert.get("subject", ())),
        issuer=_flatten_name(cert.get("issuer", ())),
        serial_number=str(cert.get("serialNumber")) if cert.get("serialNumber") is not None else None,
        not_before=_parse_cert_time(cert.get("notBefore")),
        not_after=_parse_cert_time(cert.get("notAfter")),
        san_domains=san_domains,
    )

    lines = [f"TLS certificate for {domain}:"]
    if san_domains:
        lines.extend(f"- SAN: {item}" for item in san_domains)
    else:
        lines.append("- No SAN domains found.")

    return {
        "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
        "normalized": normalized.model_dump(mode="json"),
        "planner_summary": "\n".join(lines),
    }


def _tls_certificate_lookup(domain: str) -> StructuredToolOutput:
    hostname = domain.strip().lower()
    context = ssl.create_default_context()
    with socket.create_connection((hostname, 443), timeout=5) as connection:
        with context.wrap_socket(connection, server_hostname=hostname) as tls_socket:
            certificate = tls_socket.getpeercert()
    if not isinstance(certificate, dict) or not certificate:
        raise RuntimeError(f"TLS certificate lookup returned no certificate for `{hostname}`.")
    return _normalized_tls_output(hostname, certificate)


tls_certificate_lookup = Tool(
    name="tls_certificate_lookup",
    description="Fetch a TLS certificate for a domain or hostname and extract SAN domain pivots.",
    runner=_tls_certificate_lookup,
)


__all__ = [
    "tls_certificate_lookup",
]

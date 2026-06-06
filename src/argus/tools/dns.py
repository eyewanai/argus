"""DNS lookup tools for Argus."""

from __future__ import annotations

import dns.exception
import dns.resolver

from argus.tools.base import Tool


def _resolver() -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 3.0
    resolver.timeout = 2.0
    return resolver


def _format_lookup_error(hostname: str, record_type: str, exc: Exception) -> str:
    if isinstance(exc, dns.resolver.NXDOMAIN):
        return f"- No {record_type} records found for `{hostname}`."
    if isinstance(exc, dns.resolver.NoAnswer):
        return f"- No {record_type} records found for `{hostname}`."
    if isinstance(exc, dns.resolver.NoNameservers):
        return f"- DNS {record_type} lookup failed for `{hostname}`: no nameservers responded."
    if isinstance(exc, dns.resolver.LifetimeTimeout):
        return f"- DNS {record_type} lookup failed for `{hostname}`: lookup timed out."
    if isinstance(exc, dns.exception.Timeout):
        return f"- DNS {record_type} lookup failed for `{hostname}`: lookup timed out."
    return f"- DNS {record_type} lookup failed for `{hostname}`: {exc}"


def _resolve_a(hostname: str) -> str:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "A")
        addresses = [record.address for record in records]
        if not addresses:
            return f"- No A records found for `{hostname}`."
        return "\n".join(f"- A: {address}" for address in addresses)
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return _format_lookup_error(hostname, "A", exc)


def _resolve_aaaa(hostname: str) -> str:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "AAAA")
        addresses = [record.address for record in records]
        if not addresses:
            return f"- No AAAA records found for `{hostname}`."
        return "\n".join(f"- AAAA: {address}" for address in addresses)
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return _format_lookup_error(hostname, "AAAA", exc)


def _resolve_mx(hostname: str) -> str:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "MX")
        entries = [
            f"- MX: priority {record.preference} exchange {record.exchange.to_text()}"
            for record in records
        ]
        if not entries:
            return f"- No MX records found for `{hostname}`."
        return "\n".join(entries)
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return _format_lookup_error(hostname, "MX", exc)


def _resolve_soa(hostname: str) -> str:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "SOA")
        record = records[0]
        lines = [
            f"- SOA: mname {record.mname.to_text()}",
            f"- SOA: rname {record.rname.to_text()}",
            f"- SOA: serial {record.serial}",
            f"- SOA: refresh {record.refresh}",
            f"- SOA: retry {record.retry}",
            f"- SOA: expire {record.expire}",
            f"- SOA: minimum {record.minimum}",
        ]
        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return _format_lookup_error(hostname, "SOA", exc)


def _resolve_txt(hostname: str) -> str:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "TXT")
        entries: list[str] = []
        for record in records:
            text = b"".join(record.strings).decode("utf-8", errors="replace")
            entries.append(f'- TXT: "{text}"')
        if not entries:
            return f"- No TXT records found for `{hostname}`."
        return "\n".join(entries)
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return _format_lookup_error(hostname, "TXT", exc)


dns_a_lookup = Tool(
    name="dns_a_lookup",
    description="Resolve A and AAAA records for a domain or hostname.",
    runner=lambda hostname: "\n".join(
        [
            _resolve_a(hostname),
            _resolve_aaaa(hostname),
        ]
    ).strip(),
)

dns_mx_lookup = Tool(
    name="dns_mx_lookup",
    description="Resolve MX records for a domain or hostname.",
    runner=_resolve_mx,
)

dns_soa_lookup = Tool(
    name="dns_soa_lookup",
    description="Resolve the SOA record for a domain or hostname.",
    runner=_resolve_soa,
)

dns_txt_lookup = Tool(
    name="dns_txt_lookup",
    description="Resolve TXT records for a domain or hostname.",
    runner=_resolve_txt,
)

__all__ = [
    "dns_a_lookup",
    "dns_mx_lookup",
    "dns_soa_lookup",
    "dns_txt_lookup",
]

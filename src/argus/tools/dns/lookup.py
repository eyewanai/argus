"""DNS lookup tools for Argus."""

from __future__ import annotations

import json
import re
import socket

import dns.exception
import dns.resolver

from argus.tools.base import StructuredToolOutput, Tool
from argus.tools.dns.models import (
    DNSLookupResult,
    DNSRecord,
    MXLookupResult,
    MXRecord,
    NSLookupResult,
    ReverseDNSResult,
    SOALookupResult,
    SOARecord,
    TXTLookupResult,
    TXTRecord,
)


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


def _records_output(query: str, record_type: str, records: list[DNSRecord], summary_lines: list[str]) -> StructuredToolOutput:
    normalized = DNSLookupResult(
        query=query,
        record_type=record_type,
        records=records,
    )
    return {
        "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
        "normalized": normalized.model_dump(mode="json"),
        "planner_summary": "\n".join(summary_lines),
    }


def _dedupe_records(records: list[DNSRecord]) -> list[DNSRecord]:
    deduped: list[DNSRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        key = (record.name.lower(), record.record_type, record.value.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _resolve_a(hostname: str) -> list[DNSRecord]:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "A")
        return [
            DNSRecord(name=hostname, record_type="A", value=record.address)
            for record in records
            if record.address
        ]
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        raise RuntimeError(_format_lookup_error(hostname, "A", exc)) from exc


def _resolve_aaaa(hostname: str) -> list[DNSRecord]:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "AAAA")
        return [
            DNSRecord(name=hostname, record_type="AAAA", value=record.address)
            for record in records
            if record.address
        ]
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        raise RuntimeError(_format_lookup_error(hostname, "AAAA", exc)) from exc


def _resolve_address_records(hostname: str) -> StructuredToolOutput:
    records: list[DNSRecord] = []
    errors: list[str] = []
    for record_type, resolver_fn in (("A", _resolve_a), ("AAAA", _resolve_aaaa)):
        try:
            records.extend(resolver_fn(hostname))
        except RuntimeError as exc:
            errors.append(str(exc))

    if records:
        records = _dedupe_records(records)
        summary_lines = [f"Address records for {hostname}:"]
        summary_lines.extend(f"- {record.record_type}: {record.value}" for record in records)
        return _records_output(hostname, "A+AAAA", records, summary_lines)

    error_text = "\n".join(errors) if errors else f"- No A or AAAA records found for `{hostname}`."
    return {
        "output": error_text,
    }


def _resolve_mx(hostname: str) -> str:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "MX")
        mx_records: list[MXRecord] = []
        seen: set[tuple[str, int]] = set()
        for record in records:
            exchange = record.exchange.to_text().strip().rstrip(".").lower()
            preference = int(record.preference)
            key = (exchange, preference)
            if not exchange or key in seen:
                continue
            seen.add(key)
            mx_records.append(MXRecord(exchange=exchange, preference=preference))
        normalized = MXLookupResult(query=hostname, record_type="MX", records=mx_records)
        lines = [f"MX records for {hostname}:"]
        lines.extend(
            f"- MX: priority {record.preference} exchange {record.exchange}"
            for record in mx_records
        )
        if not mx_records:
            lines.append("- No MX records found.")
        return {
            "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
            "normalized": normalized.model_dump(mode="json"),
            "planner_summary": "\n".join(lines),
        }
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return {
            "output": _format_lookup_error(hostname, "MX", exc),
        }


def _resolve_soa(hostname: str) -> StructuredToolOutput:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "SOA")
        record = records[0]
        normalized = SOALookupResult(
            query=hostname,
            record_type="SOA",
            record=SOARecord(
                primary_nameserver=record.mname.to_text().strip().rstrip(".").lower(),
                responsible_party=record.rname.to_text().strip().rstrip(".").lower(),
                serial=int(record.serial),
                refresh=int(record.refresh),
                retry=int(record.retry),
                expire=int(record.expire),
                minimum=int(record.minimum),
            ),
        )
        soa_record = normalized.record
        assert soa_record is not None
        lines = [
            f"SOA record for {hostname}:",
            f"- Primary nameserver: {soa_record.primary_nameserver}",
        ]
        if soa_record.responsible_party:
            lines.append(f"- Responsible party: {soa_record.responsible_party}")
        if soa_record.serial is not None:
            lines.append(f"- Serial: {soa_record.serial}")
        return {
            "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
            "normalized": normalized.model_dump(mode="json"),
            "planner_summary": "\n".join(lines),
        }
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return {
            "output": _format_lookup_error(hostname, "SOA", exc),
        }


def _resolve_txt(hostname: str) -> StructuredToolOutput:
    def classify_txt_record(name: str, value: str) -> TXTRecord:
        stripped = value.strip()
        lowered = stripped.lower()
        includes: list[str] = []
        mechanisms: list[str] = []
        provider: str | None = None
        policy: str | None = None
        kind: str = "other"

        if lowered.startswith("v=spf1"):
            kind = "spf"
            for match in re.findall(r"(?i)\binclude:([^\s]+)", stripped):
                candidate = match.strip().rstrip(".").lower()
                if candidate and candidate not in includes:
                    includes.append(candidate)
            for match in re.findall(r"(?i)\b(?:ip4:[^\s]+|ip6:[^\s]+|mx\b|a\b)", stripped):
                mechanism = match.lower()
                if mechanism not in mechanisms:
                    mechanisms.append(mechanism)
        elif name.lower().startswith("_dmarc.") or lowered.startswith("v=dmarc1"):
            kind = "dmarc"
            policy_match = re.search(r"(?i)\bp=([a-z]+)", stripped)
            if policy_match:
                policy = policy_match.group(1).lower()
        elif "google-site-verification" in lowered:
            kind = "verification"
            provider = "google"
        elif "ms=" in lowered:
            kind = "verification"
            provider = "microsoft"

        return TXTRecord(
            name=name,
            value=stripped,
            kind=kind,  # type: ignore[arg-type]
            mechanisms=mechanisms,
            includes=includes,
            policy=policy,
            provider=provider,
        )

    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "TXT")
        txt_records: list[TXTRecord] = []
        seen_values: set[str] = set()
        for record in records:
            text = b"".join(record.strings).decode("utf-8", errors="replace")
            dedupe_key = text.strip()
            if not dedupe_key or dedupe_key in seen_values:
                continue
            seen_values.add(dedupe_key)
            txt_records.append(classify_txt_record(hostname, text))
        normalized = TXTLookupResult(query=hostname, records=txt_records)
        lines = [f"TXT records for {hostname}:"]
        if not txt_records:
            lines.append("- No TXT records found.")
        for record in txt_records[:5]:
            if record.kind == "spf":
                summary = "- SPF record"
                if record.includes:
                    summary += f" includes {', '.join(record.includes)}"
                lines.append(summary)
            elif record.kind == "dmarc":
                policy_text = record.policy or "unknown"
                lines.append(f"- DMARC policy: {policy_text}")
            elif record.kind == "verification":
                provider_text = record.provider or "unknown"
                lines.append(f"- Verification token for {provider_text}")
            else:
                preview = record.value if len(record.value) <= 80 else f"{record.value[:77]}..."
                lines.append(f"- TXT: {preview}")
        if len(txt_records) > 5:
            lines.append(f"- Additional TXT records: {len(txt_records) - 5}")
        return {
            "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
            "normalized": normalized.model_dump(mode="json"),
            "planner_summary": "\n".join(lines),
        }
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return {
            "output": _format_lookup_error(hostname, "TXT", exc),
        }


def _resolve_ns(hostname: str) -> StructuredToolOutput:
    resolver = _resolver()
    try:
        records = resolver.resolve(hostname, "NS")
        nameservers: list[str] = []
        dns_records: list[DNSRecord] = []
        for record in records:
            candidate = record.to_text().strip().rstrip(".").lower()
            if candidate and candidate not in nameservers:
                nameservers.append(candidate)
                dns_records.append(DNSRecord(name=hostname, record_type="NS", value=candidate))
        normalized_records = _dedupe_records(dns_records)
        normalized = NSLookupResult(
            query=hostname,
            record_type="NS",
            records=normalized_records,
            nameservers=nameservers,
        )
        lines = [f"NS records for {hostname}:"]
        lines.extend(f"- NS: {item}" for item in nameservers)
        if not nameservers:
            lines.append("- No NS records found.")
        return {
            "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
            "normalized": normalized.model_dump(mode="json"),
            "planner_summary": "\n".join(lines),
        }
    except Exception as exc:  # pragma: no cover - dnspython exceptions are runtime-specific
        return {
            "output": _format_lookup_error(hostname, "NS", exc),
        }


def _reverse_resolve(ip_address: str) -> StructuredToolOutput:
    try:
        hostname, _aliases, _addresses = socket.gethostbyaddr(ip_address)
    except socket.herror:
        normalized = ReverseDNSResult(query=ip_address, record_type="PTR", records=[], hostname=None)
        return {
            "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
            "normalized": normalized.model_dump(mode="json"),
            "planner_summary": f"Reverse DNS for {ip_address}:\n- No PTR hostname found.",
        }
    except OSError as exc:  # pragma: no cover - runtime-specific networking failure
        return {
            "output": f"- Reverse DNS lookup failed for `{ip_address}`: {exc}",
        }

    ptr_hostname = hostname.rstrip(".").lower()
    records = _dedupe_records([DNSRecord(name=ip_address, record_type="PTR", value=ptr_hostname)])
    normalized = ReverseDNSResult(query=ip_address, record_type="PTR", records=records, hostname=ptr_hostname)
    return {
        "output": json.dumps(normalized.model_dump(mode="json"), indent=2, sort_keys=True),
        "normalized": normalized.model_dump(mode="json"),
        "planner_summary": f"Reverse DNS for {ip_address}:\n- PTR: {normalized.hostname}",
    }


dns_a_lookup = Tool(
    name="dns_a_lookup",
    description="Resolve A and AAAA records for a domain or hostname.",
    runner=_resolve_address_records,
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

dns_ns_lookup = Tool(
    name="dns_ns_lookup",
    description="Resolve NS records for a domain and extract nameserver pivots.",
    runner=_resolve_ns,
)

reverse_dns_lookup = Tool(
    name="reverse_dns_lookup",
    description="Resolve a PTR hostname for an IP address.",
    runner=_reverse_resolve,
)

__all__ = [
    "dns_a_lookup",
    "dns_mx_lookup",
    "dns_ns_lookup",
    "reverse_dns_lookup",
    "dns_soa_lookup",
    "dns_txt_lookup",
]

"""DNS lookup tool for Argus."""

from __future__ import annotations

import socket

from argus.tools.base import Tool


def _dns_lookup(hostname: str) -> str:
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        lines: list[str] = []
        seen: set[str] = set()
        for family, socktype, proto, canonname, sockaddr in records:
            address = sockaddr[0]
            record = f"- {family.name}: {address}"
            if canonname:
                record += f" (canonname: {canonname})"
            if record not in seen:
                seen.add(record)
                lines.append(record)
        return "\n".join(lines) if lines else f"- No DNS records found for `{hostname}`."
    except OSError as exc:
        return f"- DNS lookup failed for `{hostname}`: {exc}"


dns_lookup = Tool(
    name="dns_lookup",
    description="Resolve a hostname to DNS records using the standard library.",
    runner=_dns_lookup,
)

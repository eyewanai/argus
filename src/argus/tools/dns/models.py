"""Pydantic models for DNS-derived investigation results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DNSRecordType = Literal["A", "AAAA", "NS", "MX", "TXT", "SOA", "PTR", "CNAME"]
DNSQueryType = Literal["A", "AAAA", "A+AAAA", "NS", "MX", "TXT", "SOA", "PTR", "CNAME"]


class DNSResult(BaseModel):
    query: str
    record_type: DNSQueryType


class DNSRecord(BaseModel):
    name: str
    record_type: DNSRecordType
    value: str


class DNSLookupResult(DNSResult):
    records: list[DNSRecord] = Field(default_factory=list)


class MXRecord(BaseModel):
    exchange: str
    preference: int


class MXLookupResult(DNSResult):
    records: list[MXRecord] = Field(default_factory=list)


class TXTRecord(BaseModel):
    name: str
    value: str
    kind: Literal["spf", "dmarc", "verification", "other"]
    mechanisms: list[str] = Field(default_factory=list)
    includes: list[str] = Field(default_factory=list)
    policy: str | None = None
    provider: str | None = None


class TXTLookupResult(DNSResult):
    record_type: Literal["TXT"] = "TXT"
    records: list[TXTRecord] = Field(default_factory=list)


class SOARecord(BaseModel):
    primary_nameserver: str
    responsible_party: str | None = None
    serial: int | None = None
    refresh: int | None = None
    retry: int | None = None
    expire: int | None = None
    minimum: int | None = None


class SOALookupResult(DNSResult):
    record: SOARecord | None = None


class NSLookupResult(DNSLookupResult):
    nameservers: list[str] = Field(default_factory=list)


class ReverseDNSResult(DNSLookupResult):
    hostname: str | None = None


__all__ = [
    "DNSLookupResult",
    "DNSRecord",
    "DNSRecordType",
    "DNSResult",
    "MXLookupResult",
    "MXRecord",
    "NSLookupResult",
    "ReverseDNSResult",
    "SOALookupResult",
    "SOARecord",
    "TXTLookupResult",
    "TXTRecord",
]

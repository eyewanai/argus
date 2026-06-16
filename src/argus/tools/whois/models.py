"""Normalized registration models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegistrationContact(BaseModel):
    role: Literal["abuse", "administrative", "technical", "registrant"]
    name: str | None = None
    email: str | None = None
    handle: str | None = None
    tel: str | None = None
    rir: str | None = None


class RegistrationRawRefs(BaseModel):
    rdap_url: str | None = None
    whois_server: str | None = None
    terms_of_service_url: str | None = None


class NormalizedIpRegistration(BaseModel):
    queried_ip: str
    network: str | None = None
    ip_version: int | None = None
    country: str | None = None
    rir: str | None = None
    name: str | None = None
    description: list[str] = Field(default_factory=list)
    assignment_type: str | None = None
    handle: str | None = None
    parent_handle: str | None = None
    registration_date: datetime | None = None
    last_changed_date: datetime | None = None
    expiration_date: datetime | None = None
    abuse_contacts: list[RegistrationContact] = Field(default_factory=list)
    admin_contacts: list[RegistrationContact] = Field(default_factory=list)
    technical_contacts: list[RegistrationContact] = Field(default_factory=list)
    registrant_contacts: list[RegistrationContact] = Field(default_factory=list)


class NormalizedDomainRegistration(BaseModel):
    domain: str
    registrar: str | None = None
    registrar_url: str | None = None
    registrar_abuse_email: str | None = None
    registrar_abuse_phone: str | None = None
    registrant_name: str | None = None
    registrant_org: str | None = None
    registrant_email: str | None = None
    registrant_country: str | None = None
    admin_email: str | None = None
    tech_email: str | None = None
    nameservers: list[str] = Field(default_factory=list)
    status: list[str] = Field(default_factory=list)
    creation_date: datetime | None = None
    updated_date: datetime | None = None
    expiration_date: datetime | None = None


class NormalizedRegistrationResult(BaseModel):
    query: str
    query_type: Literal["domain", "ip"]
    source: Literal["whois", "rdap"]
    domain: NormalizedDomainRegistration | None = None
    ip_network: NormalizedIpRegistration | None = None
    raw_refs: RegistrationRawRefs | None = None

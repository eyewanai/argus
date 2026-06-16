"""Pydantic models for TLS certificate investigation results."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TLSCertificateResult(BaseModel):
    domain: str
    subject: str | None = None
    issuer: str | None = None
    serial_number: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    san_domains: list[str] = Field(default_factory=list)


__all__ = [
    "TLSCertificateResult",
]

"""Pydantic models used by Argus."""

from argus.tools.whois.models import (
    NormalizedDomainRegistration,
    NormalizedIpRegistration,
    NormalizedRegistrationResult,
    RegistrationContact,
    RegistrationRawRefs,
)

__all__ = [
    "NormalizedDomainRegistration",
    "NormalizedIpRegistration",
    "NormalizedRegistrationResult",
    "RegistrationContact",
    "RegistrationRawRefs",
]

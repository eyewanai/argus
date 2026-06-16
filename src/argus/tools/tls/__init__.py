"""TLS certificate lookup tools."""

from argus.tools.tls.lookup import tls_certificate_lookup
from argus.tools.tls.models import TLSCertificateResult

__all__ = [
    "TLSCertificateResult",
    "tls_certificate_lookup",
]

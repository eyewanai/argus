"""DNS lookup tools."""

from argus.tools.dns.lookup import (
    dns_a_lookup,
    dns_mx_lookup,
    dns_ns_lookup,
    dns_soa_lookup,
    dns_txt_lookup,
    reverse_dns_lookup,
)
from argus.tools.dns.models import (
    DNSLookupResult,
    DNSRecord,
    DNSResult,
    MXLookupResult,
    MXRecord,
    NSLookupResult,
    ReverseDNSResult,
    SOALookupResult,
    SOARecord,
    TXTLookupResult,
    TXTRecord,
)

__all__ = [
    "DNSLookupResult",
    "DNSRecord",
    "DNSResult",
    "MXLookupResult",
    "MXRecord",
    "NSLookupResult",
    "ReverseDNSResult",
    "SOALookupResult",
    "SOARecord",
    "TXTLookupResult",
    "TXTRecord",
    "dns_a_lookup",
    "dns_mx_lookup",
    "dns_ns_lookup",
    "reverse_dns_lookup",
    "dns_soa_lookup",
    "dns_txt_lookup",
]

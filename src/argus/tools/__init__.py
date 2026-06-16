"""Tool package for Argus."""

from .base import Tool, ToolResult
from .dns import (
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
    dns_a_lookup,
    dns_mx_lookup,
    dns_ns_lookup,
    dns_soa_lookup,
    dns_txt_lookup,
    reverse_dns_lookup,
)
from .entity import normalize_entity
from .mcp import (
    MCPNormalizedEntity,
    MCPNormalizedFindings,
    MCPNormalizedRelationship,
    MCPNormalizedResult,
    MCPRegistry,
    MCPToolAdapter,
    build_mcp_registry,
    build_mcp_result,
)
from .registry import ToolRegistry, build_tool_registry
from .tls import TLSCertificateResult, tls_certificate_lookup
from .whois import (
    normalize_domain_registration_result,
    normalize_ip_rdap_result,
    registration_lookup,
)

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "DNSLookupResult",
    "DNSRecord",
    "DNSResult",
    "MXLookupResult",
    "MXRecord",
    "MCPNormalizedEntity",
    "MCPNormalizedFindings",
    "MCPNormalizedRelationship",
    "MCPNormalizedResult",
    "MCPRegistry",
    "MCPToolAdapter",
    "NSLookupResult",
    "ReverseDNSResult",
    "SOALookupResult",
    "SOARecord",
    "TXTLookupResult",
    "TXTRecord",
    "TLSCertificateResult",
    "build_tool_registry",
    "build_mcp_registry",
    "build_mcp_result",
    "dns_a_lookup",
    "dns_mx_lookup",
    "dns_ns_lookup",
    "reverse_dns_lookup",
    "dns_soa_lookup",
    "dns_txt_lookup",
    "normalize_domain_registration_result",
    "normalize_entity",
    "normalize_ip_rdap_result",
    "registration_lookup",
    "tls_certificate_lookup",
]

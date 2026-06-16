from __future__ import annotations

import json
import socket
import unittest
from unittest.mock import patch

from argus.core.graph import _extract_entities_from_tool_result, _pending_investigation_selection
from argus.exporters.serialization import serialize_state
from argus.tools.dns.lookup import (
    dns_a_lookup,
    dns_mx_lookup,
    dns_ns_lookup,
    dns_soa_lookup,
    dns_txt_lookup,
    reverse_dns_lookup,
)
from argus.tools.tls.lookup import tls_certificate_lookup


class _FakeSocket:
    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeTLSSocket(_FakeSocket):
    def getpeercert(self) -> dict:
        return {
            "subject": ((("commonName", "nejva.me"),),),
            "issuer": ((("commonName", "Example CA"),),),
            "serialNumber": "123456",
            "notBefore": "Jun 13 10:00:00 2026 GMT",
            "notAfter": "Jun 13 10:00:00 2027 GMT",
            "subjectAltName": [
                ("DNS", "nejva.me"),
                ("DNS", "mail.nejva.me"),
                ("DNS", "vpn.nejva.me"),
                ("DNS", "*.nejva.me"),
                ("DNS", "mail.nejva.me"),
            ],
        }


class _FakeSSLContext:
    def wrap_socket(self, connection: _FakeSocket, server_hostname: str) -> _FakeTLSSocket:
        self.server_hostname = server_hostname
        return _FakeTLSSocket()


class _FakeNSRecord:
    def __init__(self, value: str) -> None:
        self.value = value

    def to_text(self) -> str:
        return self.value


class _FakeAddressRecord:
    def __init__(self, address: str) -> None:
        self.address = address


class _FakeMXExchange:
    def __init__(self, value: str) -> None:
        self.value = value

    def to_text(self) -> str:
        return self.value


class _FakeMXRecord:
    def __init__(self, preference: int, exchange: str) -> None:
        self.preference = preference
        self.exchange = _FakeMXExchange(exchange)


class _FakeSOAName:
    def __init__(self, value: str) -> None:
        self.value = value

    def to_text(self) -> str:
        return self.value


class _FakeSOARecord:
    def __init__(self) -> None:
        self.mname = _FakeSOAName("ns3.ptsecurity.com.")
        self.rname = _FakeSOAName("hostmaster.example.com.")
        self.serial = 12345
        self.refresh = 3600
        self.retry = 600
        self.expire = 1209600
        self.minimum = 300


class _FakeTXTRecord:
    def __init__(self, *parts: bytes) -> None:
        self.strings = parts


class _FakeResolver:
    def resolve(
        self, hostname: str, record_type: str
    ) -> list[_FakeNSRecord] | list[_FakeAddressRecord] | list[_FakeMXRecord] | list[_FakeSOARecord] | list[_FakeTXTRecord]:
        if record_type == "NS":
            return [
                _FakeNSRecord("ns1.serveroid.com."),
                _FakeNSRecord("ns2.serveroid.com."),
            ]
        if record_type == "A":
            return [
                _FakeAddressRecord("91.239.26.99"),
                _FakeAddressRecord("91.239.26.99"),
            ]
        if record_type == "AAAA":
            return [_FakeAddressRecord("2001:db8::1")]
        if record_type == "MX":
            return [
                _FakeMXRecord(10, "mx1.serveroid.com."),
                _FakeMXRecord(20, "mx2.serveroid.com."),
            ]
        if record_type == "SOA":
            return [_FakeSOARecord()]
        if record_type == "TXT":
            return [
                _FakeTXTRecord(b"v=spf1 include:_spf.google.com ip4:203.0.113.10 -all"),
                _FakeTXTRecord(b"google-site-verification=abc123"),
            ]
        raise AssertionError(record_type)


class InfrastructureToolTests(unittest.TestCase):
    def test_tls_certificate_lookup_extracts_san_domains(self) -> None:
        with (
            patch("argus.tools.tls.lookup.socket.create_connection", return_value=_FakeSocket()),
            patch("argus.tools.tls.lookup.ssl.create_default_context", return_value=_FakeSSLContext()),
        ):
            result = tls_certificate_lookup.run("nejva.me")

        self.assertIsInstance(result, dict)
        normalized = result["normalized"]
        self.assertEqual(normalized["domain"], "nejva.me")
        self.assertEqual(normalized["san_domains"], ["nejva.me", "mail.nejva.me", "vpn.nejva.me"])
        json.dumps(normalized)

    def test_reverse_dns_lookup_handles_ptr_hostname(self) -> None:
        with patch("argus.tools.dns.lookup.socket.gethostbyaddr", return_value=("host123.serveroid.com", [], [])):
            result = reverse_dns_lookup.run("91.239.26.99")

        self.assertEqual(result["normalized"]["hostname"], "host123.serveroid.com")
        self.assertIn("PTR: host123.serveroid.com", result["planner_summary"])

    def test_reverse_dns_lookup_handles_missing_ptr(self) -> None:
        with patch("argus.tools.dns.lookup.socket.gethostbyaddr", side_effect=socket.herror()):
            result = reverse_dns_lookup.run("91.239.26.99")

        self.assertIsNone(result["normalized"]["hostname"])
        self.assertIn("No PTR hostname found", result["planner_summary"])

    def test_dns_ns_lookup_returns_nameservers(self) -> None:
        with patch("argus.tools.dns.lookup._resolver", return_value=_FakeResolver()):
            result = dns_ns_lookup.run("nejva.me")

        self.assertEqual(result["normalized"]["nameservers"], ["ns1.serveroid.com", "ns2.serveroid.com"])
        self.assertEqual(
            [record["value"] for record in result["normalized"]["records"]],
            ["ns1.serveroid.com", "ns2.serveroid.com"],
        )

    def test_dns_a_lookup_returns_deduplicated_records(self) -> None:
        with patch("argus.tools.dns.lookup._resolver", return_value=_FakeResolver()):
            result = dns_a_lookup.run("nejva.me")

        self.assertEqual(result["normalized"]["query"], "nejva.me")
        self.assertEqual(result["normalized"]["record_type"], "A+AAAA")
        self.assertEqual(
            result["normalized"]["records"],
            [
                {"name": "nejva.me", "record_type": "A", "value": "91.239.26.99"},
                {"name": "nejva.me", "record_type": "AAAA", "value": "2001:db8::1"},
            ],
        )

    def test_dns_mx_lookup_returns_structured_records(self) -> None:
        with patch("argus.tools.dns.lookup._resolver", return_value=_FakeResolver()):
            result = dns_mx_lookup.run("nejva.me")

        self.assertEqual(result["normalized"]["query"], "nejva.me")
        self.assertEqual(result["normalized"]["record_type"], "MX")
        self.assertEqual(
            result["normalized"]["records"],
            [
                {"exchange": "mx1.serveroid.com", "preference": 10},
                {"exchange": "mx2.serveroid.com", "preference": 20},
            ],
        )

    def test_dns_soa_lookup_returns_structured_record(self) -> None:
        with patch("argus.tools.dns.lookup._resolver", return_value=_FakeResolver()):
            result = dns_soa_lookup.run("nejva.me")

        self.assertEqual(result["normalized"]["query"], "nejva.me")
        self.assertEqual(result["normalized"]["record_type"], "SOA")
        self.assertEqual(result["normalized"]["record"]["primary_nameserver"], "ns3.ptsecurity.com")
        self.assertEqual(result["normalized"]["record"]["responsible_party"], "hostmaster.example.com")

    def test_dns_txt_lookup_returns_structured_spf_and_verification_records(self) -> None:
        with patch("argus.tools.dns.lookup._resolver", return_value=_FakeResolver()):
            result = dns_txt_lookup.run("nejva.me")

        self.assertEqual(result["normalized"]["record_type"], "TXT")
        self.assertEqual(result["normalized"]["records"][0]["kind"], "spf")
        self.assertEqual(result["normalized"]["records"][0]["includes"], ["_spf.google.com"])
        self.assertEqual(result["normalized"]["records"][0]["mechanisms"], ["ip4:203.0.113.10"])
        self.assertEqual(result["normalized"]["records"][1]["kind"], "verification")
        self.assertEqual(result["normalized"]["records"][1]["provider"], "google")
        self.assertIn("SPF record", result["planner_summary"])

    def test_dns_txt_lookup_classifies_dmarc_and_generic_records(self) -> None:
        class _DMARCResolver:
            def resolve(self, hostname: str, record_type: str) -> list[_FakeTXTRecord]:
                return [_FakeTXTRecord(b"v=DMARC1; p=reject; rua=mailto:dmarc@example.com")]

        with patch("argus.tools.dns.lookup._resolver", return_value=_DMARCResolver()):
            result = dns_txt_lookup.run("_dmarc.example.com")

        self.assertEqual(result["normalized"]["records"][0]["kind"], "dmarc")
        self.assertEqual(result["normalized"]["records"][0]["policy"], "reject")

        class _GenericTXTResolver:
            def resolve(self, hostname: str, record_type: str) -> list[_FakeTXTRecord]:
                return [_FakeTXTRecord(b"custom text evidence")]

        with patch("argus.tools.dns.lookup._resolver", return_value=_GenericTXTResolver()):
            generic_result = dns_txt_lookup.run("example.com")

        self.assertEqual(generic_result["normalized"]["records"][0]["kind"], "other")

    def test_entity_extraction_adds_san_ptr_and_ns_relationships(self) -> None:
        tls_result = {
            "tool_name": "tls_certificate_lookup",
            "input": "nejva.me",
            "output": "",
            "error": "",
            "cached": False,
            "normalized": {
                "domain": "nejva.me",
                "san_domains": ["nejva.me", "mail.nejva.me", "vpn.nejva.me"],
            },
            "planner_summary": "TLS certificate for nejva.me:\n- SAN: nejva.me\n- SAN: mail.nejva.me\n- SAN: vpn.nejva.me",
        }
        reverse_result = {
            "tool_name": "reverse_dns_lookup",
            "input": "91.239.26.99",
            "output": "",
            "error": "",
            "cached": False,
            "normalized": {
                "query": "91.239.26.99",
                "record_type": "PTR",
                "hostname": "host123.serveroid.com",
                "records": [
                    {"name": "91.239.26.99", "record_type": "PTR", "value": "host123.serveroid.com"}
                ],
            },
            "planner_summary": "Reverse DNS for 91.239.26.99:\n- PTR: host123.serveroid.com",
        }
        ns_result = {
            "tool_name": "dns_ns_lookup",
            "input": "nejva.me",
            "output": "",
            "error": "",
            "cached": False,
            "normalized": {
                "query": "nejva.me",
                "record_type": "NS",
                "nameservers": ["ns1.serveroid.com", "ns2.serveroid.com"],
                "records": [
                    {"name": "nejva.me", "record_type": "NS", "value": "ns1.serveroid.com"},
                    {"name": "nejva.me", "record_type": "NS", "value": "ns2.serveroid.com"},
                ],
            },
            "planner_summary": "NS records for nejva.me:\n- NS: ns1.serveroid.com\n- NS: ns2.serveroid.com",
        }

        tls_extraction = _extract_entities_from_tool_result(tls_result)
        reverse_extraction = _extract_entities_from_tool_result(reverse_result)
        ns_extraction = _extract_entities_from_tool_result(ns_result)

        self.assertEqual(
            [rel["relationship"] for rel in tls_extraction["relationships"]],
            ["certificate_contains", "certificate_contains"],
        )
        self.assertEqual(reverse_extraction["relationships"][0]["relationship"], "reverse_resolves_to")
        self.assertEqual(
            [entity["type"] for entity in ns_extraction["entities"]],
            ["nameserver", "nameserver"],
        )

    def test_tls_extraction_skips_self_and_wildcard_entities(self) -> None:
        tls_result = {
            "tool_name": "tls_certificate_lookup",
            "input": "example.com",
            "output": "",
            "error": "",
            "cached": False,
            "normalized": {
                "domain": "example.com",
                "san_domains": ["example.com", "mail.example.com", "*.example.com", "mail.example.com"],
            },
            "planner_summary": "",
        }

        extraction = _extract_entities_from_tool_result(tls_result)

        self.assertEqual([entity["value"] for entity in extraction["entities"]], ["mail.example.com"])
        self.assertNotIn("*.example.com", [entity["value"] for entity in extraction["entities"]])

    def test_dns_txt_lookup_does_not_create_pending_entities_from_provider_domains(self) -> None:
        txt_result = {
            "tool_name": "dns_txt_lookup",
            "input": "example.com",
            "output": "",
            "error": "",
            "cached": False,
            "normalized": {
                "query": "example.com",
                "record_type": "TXT",
                "records": [
                    {
                        "name": "example.com",
                        "value": "v=spf1 include:_spf.google.com ip4:203.0.113.10 -all",
                        "kind": "spf",
                        "mechanisms": ["include:_spf.google.com", "ip4:203.0.113.10"],
                        "includes": ["_spf.google.com"],
                        "policy": None,
                        "provider": None,
                    }
                ],
            },
            "planner_summary": "TXT records for example.com:\n- SPF record includes _spf.google.com",
        }

        extraction = _extract_entities_from_tool_result(txt_result)

        self.assertEqual(extraction["entities"], [])
        self.assertEqual(extraction["relationships"], [])

    def test_dns_txt_normalized_payload_serializes_into_state(self) -> None:
        state = {
            "raw_input": "example.com",
            "entity": "example.com",
            "entity_type": "domain",
            "run_started_at": "2026-06-13T14:22:10+03:00",
            "discovered_entities": [],
            "relationships": [],
            "tool_results": [
                {
                    "tool_name": "dns_txt_lookup",
                    "input": "example.com",
                    "output": "",
                    "error": "",
                    "cached": False,
                    "normalized": {
                        "query": "example.com",
                        "record_type": "TXT",
                        "records": [
                            {
                                "name": "example.com",
                                "value": "google-site-verification=abc123",
                                "kind": "verification",
                                "mechanisms": [],
                                "includes": [],
                                "policy": None,
                                "provider": "google",
                            }
                        ],
                    },
                    "planner_summary": "TXT records for example.com:\n- Verification token for google",
                }
            ],
            "events": [],
            "snapshots": [],
            "report": "",
            "stop_reason": "",
            "skill_name": "none",
        }

        serialized = serialize_state(state)
        record = serialized["tool_runs"][0]["normalized"]["records"][0]
        self.assertEqual(record["provider"], "google")

    def test_pending_selection_prefers_higher_value_pivots_over_nameservers(self) -> None:
        state = {
            "pending_entities": [
                {
                    "value": "ns1.cloudflare.com",
                    "type": "nameserver",
                    "status": "pending",
                    "source_tool": "dns_ns_lookup",
                    "parent": "example.com",
                    "relationship": "has_nameserver",
                    "score": 0.15,
                },
                {
                    "value": "91.239.26.99",
                    "type": "ip",
                    "status": "pending",
                    "source_tool": "dns_a_lookup",
                    "parent": "example.com",
                    "relationship": "resolves_to",
                    "score": 0.9,
                },
                {
                    "value": "owner@example.com",
                    "type": "email",
                    "status": "pending",
                    "source_tool": "registration_lookup",
                    "parent": "example.com",
                    "relationship": "has_registrant_email",
                    "score": 0.45,
                },
            ],
            "tool_results": [],
        }

        tool_name, tool_input = _pending_investigation_selection(
            state, ["dns_a_lookup", "registration_lookup", "reverse_dns_lookup"]
        )

        self.assertEqual(tool_name, "registration_lookup")
        self.assertEqual(tool_input, "91.239.26.99")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from argus.core.graph import (
    _analyze_latest_tool_result,
    _build_snapshot,
    _extract_dns_a_entities,
    _extract_dns_mx_entities,
    _extract_dns_soa_entities,
    _extract_registration_entities,
    entity_type_is_queueable,
)
from argus.tools.whois.normalize import normalize_ip_rdap_result


class InvestigationMemoryTests(unittest.TestCase):
    def _base_state(self) -> dict:
        return {
            "raw_input": "phdays.com",
            "entity": "phdays.com",
            "entity_type": "domain",
            "events": [],
            "reasoning_summary": "",
            "next_action": "",
            "tool_input": "",
            "stop_reason": "",
            "run_started_at": "2026-06-13T14:22:10+03:00",
            "skill_name": "none",
            "tool_results": [],
            "steps_remaining": 5,
            "discovered_entities": [
                {
                    "value": "phdays.com",
                    "type": "domain",
                    "source_tool": "normalize_entity",
                    "parent": "phdays.com",
                    "status": "investigating",
                    "relationship": "seed",
                }
            ],
            "pending_entities": [],
            "investigated_entities": [],
            "relationships": [],
            "snapshots": [],
            "report": "",
        }

    def test_dns_a_lookup_extracts_ip_relationships(self) -> None:
        extraction = _extract_dns_a_entities(
            {
                "tool_name": "dns_a_lookup",
                "input": "phdays.com",
                "output": "",
                "error": "",
                "cached": False,
                "normalized": {
                    "query": "phdays.com",
                    "record_type": "A+AAAA",
                    "records": [
                        {"name": "phdays.com", "record_type": "A", "value": "178.248.239.191"},
                        {"name": "phdays.com", "record_type": "A", "value": "178.248.239.193"},
                    ],
                },
            }
        )
        self.assertEqual(
            [entity["value"] for entity in extraction["entities"]],
            ["178.248.239.191", "178.248.239.193"],
        )
        self.assertEqual(
            extraction["relationships"][0],
            {
                "source": "phdays.com",
                "target": "178.248.239.191",
                "relationship": "resolves_to",
            },
        )

    def test_dns_mx_lookup_extracts_domains(self) -> None:
        extraction = _extract_dns_mx_entities(
            {
                "tool_name": "dns_mx_lookup",
                "input": "phdays.com",
                "output": "",
                "error": "",
                "cached": False,
                "normalized": {
                    "query": "phdays.com",
                    "record_type": "MX",
                    "records": [
                        {"exchange": "mx1.phdays.com", "preference": 10},
                        {"exchange": "mx2.phdays.com", "preference": 20},
                    ],
                },
            }
        )
        self.assertEqual(
            [entity["value"] for entity in extraction["entities"]],
            ["mx1.phdays.com", "mx2.phdays.com"],
        )
        self.assertEqual(
            [relationship["relationship"] for relationship in extraction["relationships"]],
            ["has_mx", "has_mx"],
        )

    def test_dns_soa_lookup_extracts_nameserver(self) -> None:
        extraction = _extract_dns_soa_entities(
            {
                "tool_name": "dns_soa_lookup",
                "input": "phdays.com",
                "output": "",
                "error": "",
                "cached": False,
                "normalized": {
                    "query": "phdays.com",
                    "record_type": "SOA",
                    "record": {
                        "primary_nameserver": "ns3.ptsecurity.com",
                        "responsible_party": "hostmaster.example.com",
                        "serial": 12345,
                        "refresh": 3600,
                        "retry": 600,
                        "expire": 1209600,
                        "minimum": 300,
                    },
                },
            }
        )
        self.assertEqual([entity["value"] for entity in extraction["entities"]], ["ns3.ptsecurity.com"])
        self.assertEqual(extraction["relationships"][0]["relationship"], "has_nameserver")

    def test_registration_lookup_uses_normalized_data_only(self) -> None:
        normalized = normalize_ip_rdap_result(
            "91.239.26.99",
            {
                "url": "https://rdap.db.ripe.net/ip/91.239.26.99",
                "whois_server": "whois.ripe.net",
                "terms_of_service_url": "http://www.ripe.net/db/support/db-terms-conditions.pdf",
                "startAddress": "91.239.26.0",
                "endAddress": "91.239.26.255",
                "country": "RU",
                "name": "RU-IONICA-CUST-91-239-26-0-24-20160907",
                "entities": [
                    {
                        "roles": ["abuse"],
                        "handle": "ORG-SL612-RIPE",
                        "vcardArray": [
                            "vcard",
                            [
                                ["fn", {}, "text", "Serveroid LLC"],
                                ["email", {}, "text", "abuse@flops.ru"],
                            ],
                        ],
                    }
                ],
            },
        )
        extraction = _extract_registration_entities(
            {
                "tool_name": "registration_lookup",
                "input": "91.239.26.99",
                "output": "RDAP normalized",
                "error": "",
                "cached": False,
                "normalized": normalized.model_dump(mode="json"),
                "raw": {
                    "query": "91.239.26.99",
                    "query_type": "ip",
                    "source": "rdap",
                    "response": {
                        "url": "https://rdap.db.ripe.net/ip/91.239.26.99",
                        "whois_server": "whois.ripe.net",
                        "terms_of_service_url": "http://www.ripe.net/db/support/db-terms-conditions.pdf",
                    },
                },
                "planner_summary": "Registration lookup for 91.239.26.99:\n- Network: 91.239.26.0/24",
            }
        )
        values = [entity["value"] for entity in extraction["entities"]]
        self.assertIn("91.239.26.0/24", values)
        self.assertIn("abuse@flops.ru", values)
        self.assertIn("Serveroid LLC", values)
        self.assertNotIn("rdap.db.ripe.net", values)
        self.assertNotIn("whois.ripe.net", values)
        self.assertNotIn("www.ripe.net", values)
        self.assertNotIn("db-terms-conditions.pdf", values)

    def test_analyze_latest_tool_result_updates_memory_and_statuses(self) -> None:
        state = self._base_state()
        state["tool_results"] = [
            {
                "tool_name": "dns_mx_lookup",
                "input": "phdays.com",
                "output": "",
                "error": "",
                "cached": False,
                "normalized": {
                    "query": "phdays.com",
                    "record_type": "MX",
                    "records": [
                        {"exchange": "mx1.phdays.com", "preference": 10},
                        {"exchange": "mx2.phdays.com", "preference": 20},
                    ],
                },
            }
        ]

        discovered, pending, investigated, relationships, events = _analyze_latest_tool_result(state)

        self.assertIn("phdays.com", investigated)
        self.assertEqual(
            [entity["value"] for entity in pending],
            ["mx1.phdays.com", "mx2.phdays.com"],
        )
        self.assertEqual(
            relationships,
            [
                {
                    "source": "phdays.com",
                    "target": "mx1.phdays.com",
                    "relationship": "has_mx",
                },
                {
                    "source": "phdays.com",
                    "target": "mx2.phdays.com",
                    "relationship": "has_mx",
                },
            ],
        )
        self.assertTrue(any("Queued entity mx1.phdays.com" in event for event in events))
        self.assertEqual(discovered[0]["status"], "done")

    def test_snapshot_captures_selected_action_and_queue(self) -> None:
        state = self._base_state()
        state["pending_entities"] = [
            {
                "value": "flops.ru",
                "type": "domain",
                "source_tool": "registration_lookup",
                "parent": "91.239.26.99",
                "status": "pending",
                "relationship": "references_domain",
                "score": 0.91,
            },
            {
                "value": "rdap.db.ripe.net",
                "type": "domain",
                "source_tool": "registration_lookup",
                "parent": "91.239.26.99",
                "status": "pending",
                "relationship": "references_domain",
            },
        ]
        state["discovered_entities"].extend(state["pending_entities"])
        state["relationships"] = [
            {
                "source": "91.239.26.99",
                "target": "flops.ru",
                "relationship": "references_domain",
            }
        ]
        state["tool_results"] = [
            {
                "tool_name": "dns_a_lookup",
                "input": "nejva.me",
                "output": "- A: 91.239.26.99",
                "error": "",
                "cached": False,
            }
        ]

        snapshot = _build_snapshot(
            state,
            "registration_lookup",
            "flops.ru",
            "Likely owner domain referenced from IP registration",
            "",
        )

        self.assertEqual(snapshot["step"], 1)
        self.assertEqual(snapshot["selected"]["entity"], "flops.ru")
        self.assertEqual(snapshot["selected"]["tool"], "registration_lookup")
        self.assertEqual(snapshot["queue"][0]["source"], "91.239.26.99")
        self.assertEqual(snapshot["queue"][0]["score"], 0.91)
        self.assertEqual(snapshot["tool_runs_count"], 1)

    def test_queueable_entity_types_are_centralized(self) -> None:
        for entity_type in ("domain", "ip", "hostname", "nameserver", "email"):
            self.assertTrue(entity_type_is_queueable(entity_type))

        for entity_type in ("network", "country", "rir", "registrar", "status", "description", "organization"):
            self.assertFalse(entity_type_is_queueable(entity_type))

    def test_nameserver_discovers_parent_domain_with_lower_priority(self) -> None:
        state = self._base_state()
        state["tool_results"] = [
            {
                "tool_name": "dns_ns_lookup",
                "input": "nejva.me",
                "output": "",
                "error": "",
                "cached": False,
                "normalized": {
                    "query": "nejva.me",
                    "record_type": "NS",
                    "nameservers": ["nsu0.serveroid.com"],
                    "records": [
                        {"name": "nejva.me", "record_type": "NS", "value": "nsu0.serveroid.com"},
                    ],
                },
            }
        ]

        discovered, pending, _investigated, relationships, events = _analyze_latest_tool_result(state)

        pending_by_value = {entity["value"]: entity for entity in pending}
        self.assertIn("nsu0.serveroid.com", pending_by_value)
        self.assertIn("serveroid.com", pending_by_value)
        self.assertLess(float(pending_by_value["serveroid.com"]["score"]), float(pending_by_value["nsu0.serveroid.com"]["score"]))
        self.assertIn(
            {
                "source": "nsu0.serveroid.com",
                "target": "serveroid.com",
                "relationship": "parent_domain",
            },
            relationships,
        )
        self.assertTrue(any("Queued entity serveroid.com" in event for event in events))
        self.assertTrue(any(entity["value"] == "serveroid.com" for entity in discovered))


if __name__ == "__main__":
    unittest.main()

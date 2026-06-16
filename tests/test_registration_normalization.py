from __future__ import annotations

import unittest

from argus.core.graph import _analyze_latest_tool_result, _format_tool_results
from argus.exporters.markdown import export_report_markdown
from argus.exporters.serialization import serialize_state
from argus.tools.whois.normalize import normalize_ip_rdap_result


class RegistrationNormalizationTests(unittest.TestCase):
    def _rdap_payload(self) -> dict:
        return {
            "url": "https://rdap.db.ripe.net/ip/91.239.26.99",
            "whois_server": "whois.ripe.net",
            "terms_of_service_url": "http://www.ripe.net/db/support/db-terms-conditions.pdf",
            "startAddress": "91.239.26.0",
            "endAddress": "91.239.26.255",
            "country": "RU",
            "name": "RU-IONICA-CUST-91-239-26-0-24-20160907",
            "remarks": [{"description": ["Legacy IP space for Ionica customers"]}],
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
                    "url": "https://rdap.db.ripe.net/entity/ORG-SL612-RIPE",
                }
            ],
        }

    def _state_with_registration(self) -> dict:
        normalized = normalize_ip_rdap_result("91.239.26.99", self._rdap_payload())
        return {
            "raw_input": "91.239.26.99",
            "entity": "91.239.26.99",
            "entity_type": "ip",
            "events": [],
            "reasoning_summary": "",
            "next_action": "",
            "tool_input": "",
            "stop_reason": "",
            "run_started_at": "2026-06-13T14:22:10+03:00",
            "skill_name": "none",
            "tool_results": [
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
                        "response": self._rdap_payload(),
                    },
                    "planner_summary": (
                        "Registration lookup for 91.239.26.99:\n"
                        "- Network: 91.239.26.0/24\n"
                        "- Country: RU\n"
                        "- Abuse contact: Serveroid LLC <abuse@flops.ru>"
                    ),
                }
            ],
            "steps_remaining": 4,
            "discovered_entities": [
                {
                    "value": "91.239.26.99",
                    "type": "ip",
                    "source_tool": "normalize_entity",
                    "parent": "91.239.26.99",
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

    def test_normalize_ip_rdap_result_preserves_raw_refs_and_useful_fields(self) -> None:
        normalized = normalize_ip_rdap_result("91.239.26.99", self._rdap_payload())

        self.assertEqual(normalized.ip_network.network, "91.239.26.0/24")
        self.assertEqual(normalized.ip_network.country, "RU")
        self.assertEqual(normalized.ip_network.abuse_contacts[0].email, "abuse@flops.ru")
        self.assertEqual(normalized.ip_network.abuse_contacts[0].name, "Serveroid LLC")
        self.assertEqual(normalized.raw_refs.whois_server, "whois.ripe.net")

    def test_service_metadata_is_not_added_to_pending_entities(self) -> None:
        state = self._state_with_registration()

        discovered, pending, _investigated, relationships, _events = _analyze_latest_tool_result(state)

        pending_values = [entity["value"] for entity in pending]
        discovered_values = [entity["value"] for entity in discovered]
        self.assertIn("91.239.26.0/24", discovered_values)
        self.assertIn("RU", discovered_values)
        self.assertIn("RIPE", discovered_values)
        self.assertIn("RU-IONICA-CUST-91-239-26-0-24-20160907", discovered_values)
        self.assertIn("Legacy IP space for Ionica customers", discovered_values)
        self.assertIn("Serveroid LLC", discovered_values)
        self.assertIn("abuse@flops.ru", pending_values)
        self.assertNotIn("91.239.26.0/24", pending_values)
        self.assertNotIn("RU", pending_values)
        self.assertNotIn("RIPE", pending_values)
        self.assertNotIn("RU-IONICA-CUST-91-239-26-0-24-20160907", pending_values)
        self.assertNotIn("Legacy IP space for Ionica customers", pending_values)
        self.assertNotIn("Serveroid LLC", pending_values)
        self.assertNotIn("rdap.db.ripe.net", pending_values)
        self.assertNotIn("whois.ripe.net", pending_values)
        self.assertNotIn("www.ripe.net", pending_values)
        self.assertNotIn("db-terms-conditions.pdf", pending_values)
        self.assertIn(
            {
                "source": "91.239.26.99",
                "target": "91.239.26.0/24",
                "relationship": "belongs_to_network",
            },
            relationships,
        )
        self.assertIn(
            {
                "source": "91.239.26.0/24",
                "target": "abuse@flops.ru",
                "relationship": "has_abuse_contact",
            },
            relationships,
        )
        self.assertIn(
            {
                "source": "91.239.26.0/24",
                "target": "Serveroid LLC",
                "relationship": "has_abuse_org",
            },
            relationships,
        )

    def test_planner_context_uses_summary_not_raw_payload(self) -> None:
        state = self._state_with_registration()

        prompt_fragment = _format_tool_results(state["tool_results"])

        self.assertIn("Registration lookup for 91.239.26.99:", prompt_fragment)
        self.assertNotIn("rdap.db.ripe.net", prompt_fragment)
        self.assertNotIn("whois.ripe.net", prompt_fragment)
        self.assertNotIn("db-terms-conditions.pdf", prompt_fragment)

    def test_report_uses_normalized_summary_not_raw_payload(self) -> None:
        state = self._state_with_registration()
        discovered, pending, investigated, relationships, events = _analyze_latest_tool_result(state)
        state["discovered_entities"] = discovered
        state["pending_entities"] = pending
        state["investigated_entities"] = investigated
        state["relationships"] = relationships
        state["events"] = events

        report = export_report_markdown(state)

        self.assertIn("91.239.26.0/24", report)
        self.assertIn("abuse@flops.ru", report)
        self.assertNotIn("rdap.db.ripe.net", report)
        self.assertNotIn("whois.ripe.net", report)
        self.assertNotIn("db-terms-conditions.pdf", report)

    def test_state_serialization_keeps_raw_payload(self) -> None:
        state = self._state_with_registration()

        serialized = serialize_state(state)
        tool_run = serialized["tool_runs"][0]

        self.assertIn("raw", tool_run)
        self.assertIn("normalized", tool_run)
        raw_response = tool_run["raw"]["response"]
        self.assertEqual(raw_response["whois_server"], "whois.ripe.net")
        self.assertIn("db-terms-conditions.pdf", raw_response["terms_of_service_url"])


if __name__ == "__main__":
    unittest.main()

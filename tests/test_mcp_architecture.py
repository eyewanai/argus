from __future__ import annotations

import unittest

from argus.core.graph import _extract_entities_from_tool_result
from argus.tools.base import make_tool_result
from argus.tools.mcp import (
    MCPNormalizedEntity,
    MCPNormalizedFindings,
    MCPToolAdapter,
    build_mcp_result,
)
from argus.tools.registry import ToolRegistry


class _FakePassiveDNSAdapter(MCPToolAdapter):
    name = "mcp_passive_dns_lookup"
    description = "Future Passive DNS lookup through MCP."
    server_name = "passive-dns"

    async def call(self, input_value: str):
        findings = MCPNormalizedFindings(
            entities=[
                MCPNormalizedEntity(
                    value="example.com",
                    type="domain",
                    parent=input_value,
                    relationship="passive_resolves_to",
                    classification="passive_dns_domain",
                    score=0.8,
                )
            ],
            events=[f"Observed passive DNS domain example.com for {input_value}"],
        )
        return build_mcp_result(
            tool_name=self.name,
            input_value=input_value,
            source="mcp:passive-dns",
            finding_kind="passive_dns",
            query=input_value,
            summary={
                "query": input_value,
                "records": [
                    {
                        "domain": "example.com",
                        "first_seen": "2026-06-01T00:00:00Z",
                        "last_seen": "2026-06-13T00:00:00Z",
                    }
                ],
            },
            findings=findings,
            raw={"records": [{"fqdn": "example.com"}]},
            planner_summary="Passive DNS for 91.239.26.99:\n- example.com",
            output="Passive DNS returned 1 domain for 91.239.26.99.",
        )


class MCPArchitectureTests(unittest.TestCase):
    def test_make_tool_result_populates_required_contract_fields(self) -> None:
        result = make_tool_result(
            tool_name="plain_tool",
            input_value="example.com",
            output="Human readable output",
        )

        self.assertEqual(result["tool_name"], "plain_tool")
        self.assertEqual(result["input"], "example.com")
        self.assertEqual(result["output"], "Human readable output")
        self.assertEqual(result["error"], "")
        self.assertFalse(result["cached"])
        self.assertEqual(result["planner_summary"], "Human readable output")
        self.assertEqual(result["raw"], None)
        self.assertEqual(result["normalized"]["findings"]["entities"], [])

    def test_async_mcp_adapter_runs_through_standard_tool_registry(self) -> None:
        registry = ToolRegistry(
            tools={
                "mcp_passive_dns_lookup": _FakePassiveDNSAdapter().as_tool(),
            }
        )

        result = registry.run("mcp_passive_dns_lookup", "91.239.26.99")

        self.assertEqual(result["tool_name"], "mcp_passive_dns_lookup")
        self.assertEqual(result["planner_summary"], "Passive DNS for 91.239.26.99:\n- example.com")
        self.assertEqual(result["normalized"]["finding_kind"], "passive_dns")
        self.assertEqual(result["normalized"]["summary"]["query"], "91.239.26.99")

    def test_graph_extracts_generic_normalized_findings_without_tool_specific_branch(self) -> None:
        result = build_mcp_result(
            tool_name="mcp_passive_dns_lookup",
            input_value="91.239.26.99",
            source="mcp:passive-dns",
            finding_kind="passive_dns",
            query="91.239.26.99",
            summary={
                "query": "91.239.26.99",
                "records": [
                    {
                        "domain": "example.com",
                        "first_seen": "2026-06-01T00:00:00Z",
                        "last_seen": "2026-06-13T00:00:00Z",
                    }
                ],
            },
            findings=MCPNormalizedFindings(
                entities=[
                    MCPNormalizedEntity(
                        value="example.com",
                        type="domain",
                        parent="91.239.26.99",
                        relationship="passive_resolves_to",
                        classification="passive_dns_domain",
                        score=0.8,
                    )
                ],
                events=["Observed passive DNS domain example.com for 91.239.26.99"],
            ),
            raw={"records": [{"fqdn": "example.com"}]},
            planner_summary="Passive DNS for 91.239.26.99:\n- example.com",
            output="Passive DNS returned 1 domain for 91.239.26.99.",
        )

        extraction = _extract_entities_from_tool_result(result)

        self.assertEqual(
            extraction["entities"],
            [
                {
                    "value": "example.com",
                    "type": "domain",
                    "source_tool": "mcp_passive_dns_lookup",
                    "parent": "91.239.26.99",
                    "status": "pending",
                    "relationship": "passive_resolves_to",
                    "classification": "passive_dns_domain",
                    "score": 0.8,
                }
            ],
        )
        self.assertEqual(
            extraction["relationships"],
            [
                {
                    "source": "91.239.26.99",
                    "target": "example.com",
                    "relationship": "passive_resolves_to",
                }
            ],
        )
        self.assertEqual(
            extraction["events"],
            ["Observed passive DNS domain example.com for 91.239.26.99"],
        )


if __name__ == "__main__":
    unittest.main()

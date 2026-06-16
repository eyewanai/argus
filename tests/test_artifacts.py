from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from argus.core.config import default_config
from argus.exporters import export_mermaid_graph, serialize_state, write_investigation_artifacts


class ArtifactExportTests(unittest.TestCase):
    def _state(self) -> dict:
        started_at = datetime.fromisoformat("2026-06-13T14:22:10+03:00")
        return {
            "raw_input": "nejva.me",
            "entity": "nejva.me",
            "entity_type": "domain",
            "run_started_at": started_at,
            "events": [
                "Started investigation of nejva.me",
                "Normalized input as nejva.me (domain)",
                "Planner selected dns_a_lookup for nejva.me: resolve domain to IPs",
            ],
            "reasoning_summary": "resolve domain to IPs",
            "next_action": "report",
            "tool_input": "",
            "stop_reason": "no remaining enabled tools.",
            "skill_name": "none",
            "tool_results": [
                {
                    "tool_name": "dns_a_lookup",
                    "input": "nejva.me",
                    "output": "- A: 91.239.26.99",
                    "error": "",
                    "cached": False,
                }
            ],
            "steps_remaining": 7,
            "discovered_entities": [
                {
                    "value": "nejva.me",
                    "type": "domain",
                    "source_tool": "normalize_entity",
                    "parent": "nejva.me",
                    "status": "done",
                    "relationship": "seed",
                },
                {
                    "value": "91.239.26.99",
                    "type": "ip",
                    "source_tool": "dns_a_lookup",
                    "parent": "nejva.me",
                    "status": "pending",
                    "relationship": "resolves_to",
                },
            ],
            "pending_entities": [
                {
                    "value": "91.239.26.99",
                    "type": "ip",
                    "source_tool": "dns_a_lookup",
                    "parent": "nejva.me",
                    "status": "pending",
                    "relationship": "resolves_to",
                    "score": None,
                }
            ],
            "investigated_entities": ["nejva.me"],
            "relationships": [
                {
                    "source": "nejva.me",
                    "target": "91.239.26.99",
                    "relationship": "resolves_to",
                },
                {
                    "source": "nejva.me",
                    "target": "91.239.26.99",
                    "relationship": "resolves_to",
                },
            ],
            "snapshots": [
                {
                    "step": 1,
                    "selected": {
                        "entity": "nejva.me",
                        "tool": "dns_a_lookup",
                        "reason": "resolve domain to IPs",
                    },
                    "queue": [],
                    "entities_count": 1,
                    "relationships_count": 0,
                    "tool_runs_count": 0,
                }
            ],
            "report": "# Investigation Report\n\n## Summary\n\nnejva.me resolved to `91.239.26.99`.\n",
        }

    def test_default_config_includes_output_defaults(self) -> None:
        config = default_config()
        self.assertEqual(config["output"]["dir"], "/tmp/argus")
        self.assertTrue(config["output"]["write_by_default"])
        self.assertIn("state.json", config["output"]["formats"])

    def test_serialize_state_converts_datetime_to_iso(self) -> None:
        serialized = serialize_state(self._state())
        self.assertEqual(serialized["run_started_at"], "2026-06-13T14:22:10+03:00")
        self.assertEqual(serialized["normalized_entity"], "nejva.me")

    def test_export_mermaid_graph_deduplicates_edges(self) -> None:
        graph = export_mermaid_graph(self._state())
        self.assertEqual(graph.count("-->|resolves_to|"), 1)
        self.assertIn('nejva_me["nejva.me<br/>domain"]', graph)

    def test_write_investigation_artifacts_creates_expected_files(self) -> None:
        state = self._state()
        config = default_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            config["output"]["dir"] = temp_dir
            written_paths = write_investigation_artifacts(state, config)

            self.assertEqual(
                [path.name for path in written_paths],
                config["output"]["formats"],
            )
            run_dir = Path(written_paths[0]).parent
            self.assertTrue(run_dir.name.startswith("nejva-me-20260613-142210"))

            snapshots = json.loads((run_dir / "snapshots.json").read_text(encoding="utf-8"))
            machine_state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertIsInstance(snapshots, list)
            self.assertEqual(machine_state["normalized_entity"], "nejva.me")
            self.assertIn("graph TD", (run_dir / "graph.mmd").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

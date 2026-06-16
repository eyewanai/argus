from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from unittest.mock import patch

from argus.core.cache import ToolCache
from argus.core.config import default_config
from argus.tools.registry import build_tool_registry


class ToolCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_path = Path(self.temp_dir.name) / "tool_cache.sqlite"

    def test_cache_key_is_stable_for_same_tool_and_input(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        first = cache._cache_key("dns_a_lookup", " Example.COM ")
        second = cache._cache_key("dns_a_lookup", "example.com")
        self.assertEqual(first, second)

    def test_cache_key_differs_for_different_tools(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        first = cache._cache_key("dns_a_lookup", "example.com")
        second = cache._cache_key("registration_lookup", "example.com")
        self.assertNotEqual(first, second)

    def test_set_and_get_round_trip(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        payload = {"output": "ok", "error": ""}
        cache.set("dns_a_lookup", "example.com", payload)
        self.assertEqual(cache.get("dns_a_lookup", "example.com"), payload)

    def test_set_and_get_round_trip_with_datetime_payload(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        payload = {
            "output": "ok",
            "error": "",
            "normalized": {
                "registration_date": datetime.fromisoformat("2026-06-13T14:22:10+03:00"),
            },
        }
        cache.set("registration_lookup", "91.239.26.99", payload)
        cached = cache.get("registration_lookup", "91.239.26.99")
        self.assertEqual(
            cached["normalized"]["registration_date"],
            "2026-06-13T14:22:10+03:00",
        )

    def test_expired_entry_is_ignored(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        cache.set("dns_a_lookup", "example.com", {"output": "ok", "error": ""})
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                "UPDATE tool_cache SET expires_at = 1 WHERE tool_name = ?",
                ("dns_a_lookup",),
            )
            connection.commit()
        self.assertIsNone(cache.get("dns_a_lookup", "example.com"))

    def test_delete_expired_returns_deleted_count(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        cache.set("dns_a_lookup", "example.com", {"output": "ok", "error": ""})
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute(
                "UPDATE tool_cache SET expires_at = 1 WHERE tool_name = ?",
                ("dns_a_lookup",),
            )
            connection.commit()
        self.assertEqual(cache.delete_expired(), 1)

    def test_readonly_cache_path_falls_back_to_tmp(self) -> None:
        cache = ToolCache(str(self.cache_path), ttl_seconds=3600)
        original_connect = sqlite3.connect
        state = {"calls": 0}

        def flaky_connect(path: str | Path, *args, **kwargs):
            if str(path) == str(self.cache_path) and state["calls"] == 0:
                state["calls"] += 1
                raise sqlite3.OperationalError("attempt to write a readonly database")
            return original_connect(path, *args, **kwargs)

        with patch("argus.core.cache.sqlite3.connect", side_effect=flaky_connect):
            cache.set("dns_a_lookup", "example.com", {"output": "ok", "error": ""})

        self.assertNotEqual(cache.path, self.cache_path)
        self.assertTrue(str(cache.path).startswith(gettempdir()))
        self.assertEqual(cache.get("dns_a_lookup", "example.com"), {"output": "ok", "error": ""})


class ToolRegistryCacheIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_path = Path(self.temp_dir.name) / "tool_cache.sqlite"

    def _config(self, *, enabled: bool = True) -> dict:
        config = default_config()
        config["cache"] = {
            "enabled": enabled,
            "ttl_seconds": 3600,
            "path": str(self.cache_path),
            "cache_errors": False,
        }
        config["tools"]["local"]["enabled"] = True
        config["tools"]["local"]["include"] = ["dns_a_lookup"]
        return config

    def test_second_run_returns_cached_result(self) -> None:
        registry = build_tool_registry(self._config())
        calls: list[str] = []

        def runner(tool_input: str) -> str:
            calls.append(tool_input)
            return "resolved"

        registry.tools["dns_a_lookup"] = registry.tools["dns_a_lookup"].__class__(
            name="dns_a_lookup",
            description="test",
            runner=runner,
        )

        first = registry.run("dns_a_lookup", "example.com")
        second = registry.run("dns_a_lookup", "example.com")

        self.assertEqual(calls, ["example.com"])
        self.assertFalse(first["cached"])
        self.assertEqual(first.get("cache_event"), "Cached result for dns_a_lookup(example.com)")
        self.assertTrue(second["cached"])
        self.assertEqual(second.get("cache_event"), "Cache hit for dns_a_lookup(example.com)")

    def test_cache_disabled_skips_cache(self) -> None:
        registry = build_tool_registry(self._config(enabled=False))
        calls: list[str] = []

        def runner(tool_input: str) -> str:
            calls.append(tool_input)
            return "resolved"

        registry.tools["dns_a_lookup"] = registry.tools["dns_a_lookup"].__class__(
            name="dns_a_lookup",
            description="test",
            runner=runner,
        )

        first = registry.run("dns_a_lookup", "example.com")
        second = registry.run("dns_a_lookup", "example.com")

        self.assertEqual(calls, ["example.com", "example.com"])
        self.assertFalse(first["cached"])
        self.assertFalse(second["cached"])
        self.assertIsNone(first.get("cache_event"))
        self.assertIsNone(second.get("cache_event"))


if __name__ == "__main__":
    unittest.main()

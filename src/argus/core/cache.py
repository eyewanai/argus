"""SQLite-backed cache for Argus tool executions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from argus.exporters.serialization import make_json_safe


class ToolCache:
    def __init__(self, path: str, ttl_seconds: int):
        self.path = Path(path).expanduser()
        self.ttl_seconds = ttl_seconds
        self._initialize_with_fallback()

    def get(self, tool_name: str, tool_input: str) -> Any | None:
        key = self._cache_key(tool_name, tool_input)
        now = int(time.time())
        try:
            with sqlite3.connect(self.path) as connection:
                row = connection.execute(
                    """
                    SELECT output_json, expires_at
                    FROM tool_cache
                    WHERE key = ?
                    """,
                    (key,),
                ).fetchone()
                if row is None:
                    return None
                output_json, expires_at = row
                if int(expires_at) <= now:
                    connection.execute("DELETE FROM tool_cache WHERE key = ?", (key,))
                    connection.commit()
                    return None
        except sqlite3.OperationalError as exc:
            if not self._is_readonly_error(exc):
                raise
            self._switch_to_fallback_path()
            return self.get(tool_name, tool_input)
        return json.loads(output_json)

    def set(self, tool_name: str, tool_input: str, output: Any) -> None:
        now = int(time.time())
        expires_at = now + self.ttl_seconds
        key = self._cache_key(tool_name, tool_input)
        serialized_output = json.dumps(make_json_safe(output), sort_keys=True)
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute(
                    """
                    INSERT INTO tool_cache (
                        key,
                        tool_name,
                        tool_input,
                        output_json,
                        created_at,
                        expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        tool_name = excluded.tool_name,
                        tool_input = excluded.tool_input,
                        output_json = excluded.output_json,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at
                    """,
                    (
                        key,
                        tool_name,
                        self.normalize_input(tool_input),
                        serialized_output,
                        now,
                        expires_at,
                    ),
                )
                connection.commit()
        except sqlite3.OperationalError as exc:
            if not self._is_readonly_error(exc):
                raise
            self._switch_to_fallback_path()
            self.set(tool_name, tool_input, output)

    def delete_expired(self) -> int:
        now = int(time.time())
        try:
            with sqlite3.connect(self.path) as connection:
                cursor = connection.execute(
                    "DELETE FROM tool_cache WHERE expires_at <= ?",
                    (now,),
                )
                connection.commit()
                return int(cursor.rowcount)
        except sqlite3.OperationalError as exc:
            if not self._is_readonly_error(exc):
                raise
            self._switch_to_fallback_path()
            return self.delete_expired()

    @staticmethod
    def normalize_input(tool_input: str) -> str:
        return tool_input.strip().casefold()

    def _cache_key(self, tool_name: str, tool_input: str) -> str:
        normalized = self.normalize_input(tool_input)
        payload = f"{tool_name}:{normalized}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_cache (
                    key TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    tool_input TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
                """
            )
            connection.commit()

    def _initialize_with_fallback(self) -> None:
        try:
            self._initialize()
        except (sqlite3.OperationalError, PermissionError, OSError) as exc:
            if isinstance(exc, sqlite3.OperationalError) and not self._is_readonly_error(exc):
                raise
            self._switch_to_fallback_path()

    def _switch_to_fallback_path(self) -> None:
        fallback_dir = Path(gettempdir()) / "argus"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        self.path = fallback_dir / "tool_cache.sqlite"
        self._initialize()

    @staticmethod
    def _is_readonly_error(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return "readonly" in message or "attempt to write a readonly database" in message


__all__ = ["ToolCache"]

"""User-editable skill loading for Argus."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from argus.skills.models import Skill

SKILLS_ROOT = Path.home() / ".config" / "argus" / "skills"
DEFAULT_SKILL_NAME = "domain-investigation"
DEFAULT_SKILL_PATH = SKILLS_ROOT / DEFAULT_SKILL_NAME / "SKILL.md"

DEFAULT_SKILL_MARKDOWN = """---
name: domain-investigation
description: Investigate domains using DNS, registration data, and discovered infrastructure.
entity_types:
  - domain
  - url
---

# Domain Investigation Skill

## Objectives

- Resolve the domain to IP addresses.
- Identify registration and ownership information.
- Identify hosting/network ownership when useful.
- Produce a concise evidence-based report.

## Rules

- Prefer evidence over assumptions.
- Do not investigate every discovered nameserver unless it is necessary.
- Do not repeat the same tool/input pair.
- Stop when the core objectives are satisfied.
- If evidence is insufficient, say so clearly.
"""


def skills_root() -> Path:
    return SKILLS_ROOT


def ensure_skills_root() -> Path:
    root = skills_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_default_skill() -> Path:
    ensure_skills_root()
    if not DEFAULT_SKILL_PATH.exists():
        DEFAULT_SKILL_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_SKILL_PATH.write_text(DEFAULT_SKILL_MARKDOWN, encoding="utf-8")
    return DEFAULT_SKILL_PATH


def load_skills() -> list[Skill]:
    ensure_skills_root()
    skill_paths = sorted(skills_root().glob("*/SKILL.md"))
    if not skill_paths:
        skill_paths = [ensure_default_skill()]

    skills: list[Skill] = []
    for path in skill_paths:
        skill = _load_skill(path)
        if skill is not None:
            skills.append(skill)

    if not skills:
        skill = _load_skill(ensure_default_skill())
        if skill is not None:
            skills.append(skill)

    skills.sort(key=lambda item: (item.name, item.path.as_posix()))
    return skills


def select_default_skill(skills: list[Skill]) -> Skill | None:
    for skill in skills:
        if skill.name == DEFAULT_SKILL_NAME:
            return skill
    return skills[0] if skills else None


def _load_skill(path: Path) -> Skill | None:
    try:
        raw_text = path.read_text(encoding="utf-8")
        metadata, body = _parse_skill_markdown(raw_text)
        name = metadata.get("name", "").strip()
        description = metadata.get("description", "").strip()
        entity_types = metadata.get("entity_types", [])
        if not name or not description or not isinstance(entity_types, list):
            return None
        entity_type_values = tuple(
            item.strip() for item in entity_types if isinstance(item, str) and item.strip()
        )
        return Skill(
            name=name,
            description=description,
            entity_types=entity_type_values,
            body=body.strip(),
            path=path,
        )
    except Exception:
        return None


def _parse_skill_markdown(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Skill file is missing YAML frontmatter.")

    frontmatter_lines: list[str] = []
    body_start = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = index + 1
            break
        frontmatter_lines.append(line)

    if body_start is None:
        raise ValueError("Skill file frontmatter is not terminated.")

    metadata = _parse_frontmatter_lines(frontmatter_lines)
    body = "\n".join(lines[body_start:])
    return metadata, body


def _parse_frontmatter_lines(lines: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines:
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("- "):
            if current_key != "entity_types":
                raise ValueError("Unexpected list item in skill frontmatter.")
            metadata.setdefault("entity_types", []).append(stripped[2:].strip())
            continue
        if ":" not in line:
            raise ValueError(f"Invalid skill frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if key == "entity_types":
            metadata[key] = []
            if value:
                metadata[key].append(value)
        else:
            metadata[key] = value
            current_key = None
    return metadata


__all__ = [
    "ensure_default_skill",
    "ensure_skills_root",
    "load_skills",
    "select_default_skill",
    "skills_root",
]

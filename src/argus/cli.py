"""CLI parsing and startup flow for Argus."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from argus.runner import run_investigation
from argus.skills import Skill, load_skills
from argus.trace import render_final_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="argus")
    parser.add_argument("entity", nargs="?")
    parser.add_argument("--skill")
    return parser.parse_args()


def read_indicator() -> str:
    if sys.stdin.isatty():
        sys.stdout.write("Indicator to investigate: ")
        sys.stdout.flush()
    entity = sys.stdin.readline().strip()
    if not entity:
        print("No indicator provided. Exiting.")
        raise SystemExit(1)
    return entity


def _find_skill_by_name(skills: list[Skill], name: str) -> Skill | None:
    for skill in skills:
        if skill.name == name:
            return skill
    return None


def _print_available_skills(console: Console, skills: list[Skill]) -> None:
    if not skills:
        console.print("Available skills: none")
        return

    console.print("Available skills:")
    for skill in skills:
        console.print(f"- {skill.name}")


def run_cli() -> None:
    console = Console()
    args = parse_args()
    console.print("Argus")
    skills = load_skills()

    selected_skill = None
    if args.skill:
        selected_skill = _find_skill_by_name(skills, args.skill)
        if selected_skill is None:
            console.print(f"Unknown skill: {args.skill}")
            _print_available_skills(console, skills)
            raise SystemExit(1)

    if args.entity:
        raw_input = args.entity
        console.print()
    else:
        raw_input = read_indicator()
        console.print()

    final_state = run_investigation(console, raw_input, selected_skill)
    render_final_report(console, final_state)


__all__ = [
    "read_indicator",
    "run_cli",
]

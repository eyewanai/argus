"""Application entrypoints for Argus."""

from argus.app.cli import run_cli
from argus.app.main import main
from argus.app.runner import InvestigationRunResult, run_investigation

__all__ = [
    "InvestigationRunResult",
    "main",
    "run_cli",
    "run_investigation",
]

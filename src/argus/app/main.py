"""Argus CLI entrypoint."""

from __future__ import annotations

from argus.app.cli import run_cli


def main() -> None:
    try:
        run_cli()
    except KeyboardInterrupt:
        print("\nAborted.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()

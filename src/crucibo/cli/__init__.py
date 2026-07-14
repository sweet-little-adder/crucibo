"""CLI dispatch — Typer v2 commands + legacy argparse shim."""

from __future__ import annotations

import sys

_V2_COMMANDS = frozenset({"ingest", "backtest", "report"})


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in _V2_COMMANDS:
        from crucibo.cli.app import app

        app()
        return

    from crucibo.cli.legacy import main as legacy_main

    legacy_main()


__all__ = ["main"]
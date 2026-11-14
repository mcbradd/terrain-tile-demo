"""Runs tilepipe from ./src of the current directory (commands run from the repo root, SPEC 4.2)."""
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path.cwd() / "src"))
    from tilepipe.cli import main as cli_main

    raise SystemExit(cli_main())

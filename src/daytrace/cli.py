from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import NoReturn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daytrace")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("activitywatch", help="summarize ActivityWatch data")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())

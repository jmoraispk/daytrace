from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfoNotFoundError

from daytrace.activitywatch import DEFAULT_SERVER, summarize_day
from daytrace.source import ActivityWatchConnectionError


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daytrace")
    commands = parser.add_subparsers(dest="command", required=True)
    activitywatch = commands.add_parser(
        "activitywatch", help="summarize ActivityWatch data"
    )
    activitywatch.add_argument("--date", required=True, type=_date)
    activitywatch.add_argument("--project")
    activitywatch.add_argument("--server", default=DEFAULT_SERVER)
    activitywatch.add_argument("--timezone", dest="timezone_name")
    activitywatch.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        markdown = summarize_day(
            args.date,
            args.project,
            server=args.server,
            timezone_name=args.timezone_name,
            warn=lambda message: print(f"warning: {message}", file=sys.stderr),
        )
    except ZoneInfoNotFoundError:
        print(f"error: invalid timezone {args.timezone_name!r}", file=sys.stderr)
        return 1
    except ValueError:
        print("error: invalid ActivityWatch server URL", file=sys.stderr)
        return 1
    except ActivityWatchConnectionError:
        print(
            f"error: ActivityWatch is not reachable at {args.server}; "
            "start ActivityWatch or pass --server",
            file=sys.stderr,
        )
        return 1

    if args.output:
        try:
            lf_markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
            args.output.write_bytes(lf_markdown.encode("utf-8"))
        except OSError:
            print(
                f"error: could not write output file {str(args.output)!r}",
                file=sys.stderr,
            )
            return 1
    else:
        sys.stdout.write(markdown)
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())

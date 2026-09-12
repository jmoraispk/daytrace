from __future__ import annotations

import argparse
import builtins
import getpass
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfoNotFoundError

from daytrace.activitywatch import DEFAULT_SERVER, collect_day
from daytrace.diagnostics import diagnostic_messages
from daytrace.json_output import render_digest_json, render_session_json
from daytrace.markdown import render_digest_markdown, render_session_markdown
from daytrace.providers import OpenAIProvider, SummaryProviderError
from daytrace.source import ActivityWatchConnectionError
from daytrace.summarize import (
    SummaryRequestTooLarge,
    SummaryValidationError,
    build_summary_request,
    summarize_bundle,
)


input = builtins.input


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
    activitywatch.add_argument("--server", default=DEFAULT_SERVER)
    activitywatch.add_argument("--timezone", dest="timezone_name")
    activitywatch.add_argument("--output", type=Path)
    activitywatch.add_argument(
        "--summary", choices=("deterministic", "ai"), default="deterministic"
    )
    activitywatch.add_argument("--provider")
    activitywatch.add_argument("--model")
    activitywatch.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    detail_mode = activitywatch.add_mutually_exclusive_group()
    detail_mode.add_argument(
        "--details", action="store_true", help="include sanitized supporting evidence"
    )
    detail_mode.add_argument(
        "--raw", action="store_true", help="show sanitized session slices"
    )
    activitywatch.add_argument(
        "--diagnostics",
        action="store_true",
        help="show only aggregate diagnostics and coverage",
    )
    activitywatch.add_argument(
        "--yes", action="store_true", help="confirm the disclosed cloud send"
    )
    return parser


def _validate_mode(args: argparse.Namespace) -> str | None:
    if args.summary == "ai" and (args.provider != "openai" or not args.model):
        return "--provider openai and --model are required with --summary ai"
    if args.summary == "deterministic" and (args.provider or args.model):
        return "--provider and --model require --summary ai"
    if args.summary == "ai" and args.diagnostics:
        return "--diagnostics cannot be combined with --summary ai"
    if args.summary == "ai" and args.raw:
        return "--raw cannot be combined with --summary ai"
    if args.yes and args.summary != "ai":
        return "--yes requires --summary ai"
    return None


def _write_atomic(path: Path, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(normalized.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _emit(text: str, output: Path | None) -> bool:
    if output is None:
        sys.stdout.write(text)
        return True
    try:
        _write_atomic(output, text)
    except OSError:
        print(
            f"error: could not write output file {str(output)!r}",
            file=sys.stderr,
        )
        return False
    return True


def _render_deterministic(bundle, args: argparse.Namespace) -> str:
    if args.format == "json":
        return render_session_json(bundle, details=args.details or args.raw)
    return render_session_markdown(bundle, details=args.details, raw=args.raw)


def _render_diagnostics(bundle, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(
            {
                "schema": "daytrace.diagnostics.v1",
                "date": bundle.day.isoformat(),
                "timezone": bundle.timezone_name,
                "focused_seconds": bundle.focused_seconds,
                "session_count": len(bundle.sessions),
                "diagnostics": [
                    {"code": item.code.value, "count": item.count}
                    for item in bundle.diagnostics
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
    focused = (
        "unavailable"
        if bundle.focused_seconds is None
        else f"{bundle.focused_seconds:g} seconds"
    )
    lines = [
        f"DayTrace diagnostics — {bundle.day.isoformat()}",
        f"Timezone: {bundle.timezone_name}",
        f"Focused activity: {focused}",
        f"Sessions: {len(bundle.sessions)}",
    ]
    lines.extend(diagnostic_messages(bundle.diagnostics) or ("no diagnostics",))
    return "\n".join(lines) + "\n"


def _openai_summary(bundle, api_key: str, model: str):
    return summarize_bundle(bundle, OpenAIProvider(api_key, model))


def _confirm_cloud_send(request, provider: str, model: str, assume_yes: bool) -> bool:
    noun = "session" if request.session_count == 1 else "sessions"
    print(
        f"About to send {request.session_count} sanitized {noun} "
        f"({request.character_count} characters) to {provider}/{model}.",
        file=sys.stderr,
    )
    categories = ", ".join(request.data_categories) or "none"
    print(f"Included categories: {categories}.", file=sys.stderr)
    if assume_yes:
        return True
    try:
        return input("Continue? [y/N] ").strip().casefold() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def _collect(args: argparse.Namespace):
    return collect_day(
        args.date,
        server=args.server,
        timezone_name=args.timezone_name,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validation_error = _validate_mode(args)
    if validation_error:
        print(f"error: {validation_error}", file=sys.stderr)
        return 1
    try:
        bundle = _collect(args)
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

    if args.diagnostics:
        return 0 if _emit(_render_diagnostics(bundle, args.format), args.output) else 1

    if args.summary == "deterministic":
        return 0 if _emit(_render_deterministic(bundle, args), args.output) else 1

    deterministic_fallback = _render_deterministic(bundle, args)
    try:
        request = build_summary_request(bundle)
        if not _confirm_cloud_send(request, args.provider, args.model, args.yes):
            print("error: cloud summary was not confirmed", file=sys.stderr)
            return 1
        try:
            api_key = getpass.getpass("OpenAI API key: ")
        except (EOFError, KeyboardInterrupt, OSError):
            print("error: could not read OpenAI API key", file=sys.stderr)
            return 1
        if not api_key:
            print("error: OpenAI API key is required", file=sys.stderr)
            return 1
        digest, provenance = _openai_summary(bundle, api_key, args.model)
        rendered = (
            render_digest_json(bundle, digest, provenance, details=args.details)
            if args.format == "json"
            else render_digest_markdown(
                bundle, digest, provenance, details=args.details
            )
        )
    except (SummaryProviderError, SummaryValidationError, SummaryRequestTooLarge):
        print(
            "warning: AI summary unavailable; using deterministic fallback",
            file=sys.stderr,
        )
        return 2 if _emit(deterministic_fallback, args.output) else 1

    return 0 if _emit(rendered, args.output) else 1


def entrypoint() -> NoReturn:
    raise SystemExit(main())

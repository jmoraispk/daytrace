from __future__ import annotations

import argparse
import builtins
import getpass
import json
import os
import sys
import tempfile
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfoNotFoundError

from daytrace import __version__
from daytrace.activitywatch import DEFAULT_SERVER, collect_day
from daytrace.cloud_privacy import CloudPrivacyError
from daytrace.diagnostics import diagnostic_messages
from daytrace.episode import compact_sessions
from daytrace.json_output import render_digest_json, render_episode_json
from daytrace.markdown import render_digest_markdown, render_episode_markdown
from daytrace.models import ProviderFailureKind
from daytrace.providers import OpenAIProvider, SummaryProviderError
from daytrace.source import ActivityWatchConnectionError
from daytrace.summarize import (
    EpisodeRequestTooLarge,
    MergeRequestTooLarge,
    SummaryRequestTooLarge,
    SummaryValidationError,
    build_summary_plan,
    summarize_bundle,
)
from daytrace.summary_diagnostics import (
    render_summary_failure_json,
    safe_failure_code,
    safe_failure_field,
    safe_identifier,
)


input = builtins.input


class _ProgressProvider:
    def __init__(self, provider: object, summary_chunks: int) -> None:
        self._provider = provider
        self._summary_chunks = summary_chunks
        self._summary_index = 0

    def _call(self, label: str, method, request):
        print(f"AI summary: {label} — waiting for OpenAI...", file=sys.stderr)
        started = time.monotonic()
        response = method(request)
        elapsed = max(0, round(time.monotonic() - started))
        print(
            f"AI summary: {label} — response received after {elapsed}s; "
            "validating...",
            file=sys.stderr,
        )
        return response

    def summarize(self, request):
        is_repair = "repair_instruction" in request.payload
        if not is_repair:
            self._summary_index += 1
        label = f"chunk {self._summary_index}/{self._summary_chunks}"
        if is_repair:
            label += " repair retry"
        return self._call(label, self._provider.summarize, request)

    def merge(self, request):
        return self._call("merge", self._provider.merge, request)


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
    activitywatch.add_argument(
        "--debug-output",
        type=Path,
        help="write privacy-safe AI failure metadata as JSON",
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
    if args.debug_output and args.summary != "ai":
        return "--debug-output requires --summary ai"
    if (
        args.output
        and args.debug_output
        and args.output.absolute() == args.debug_output.absolute()
    ):
        return "--debug-output must differ from --output"
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
    if not hasattr(bundle, "episodes"):
        bundle = compact_sessions(bundle)
    if args.format == "json":
        return render_episode_json(bundle, details=args.details, raw=args.raw)
    return render_episode_markdown(bundle, details=args.details, raw=args.raw)


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


def _openai_summary(bundle, api_key: str, model: str, plan):
    provider = _ProgressProvider(
        OpenAIProvider(api_key, model), summary_chunks=len(plan.requests)
    )
    return summarize_bundle(bundle, provider, plan)


def _confirm_cloud_send(plan, provider: str, model: str, assume_yes: bool) -> bool:
    count = plan.episode_count
    noun = "episode" if count == 1 else "episodes"
    print(
        f"About to send {count} compact {noun} to {provider}/{model}.",
        file=sys.stderr,
    )
    chunks = len(plan.requests)
    if chunks == 1:
        call_description = "1 summary call"
    else:
        call_description = f"{chunks} summary chunks plus 1 merge call"
    print(
        f"Planned calls: {call_description}; {plan.input_character_count} "
        "characters total initial input.",
        file=sys.stderr,
    )
    categories = ", ".join(plan.data_categories) or "none"
    print(f"Included categories: {categories}.", file=sys.stderr)
    print(
        "At most one automatic allocation-repair retry may be made per chunk.",
        file=sys.stderr,
    )
    if assume_yes:
        return True
    try:
        return input("Continue? [y/N] ").strip().casefold() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


def _summary_failure_message(
    exc: Exception, provider: object = "openai", model: object = "unknown"
) -> str:
    if isinstance(exc, EpisodeRequestTooLarge):
        reason = "one compact episode exceeds the safe request limit"
    elif isinstance(exc, MergeRequestTooLarge):
        reason = "the compact merge request exceeds the safe request limit"
    elif isinstance(exc, SummaryProviderError):
        reason = {
            ProviderFailureKind.AUTHENTICATION: "authentication, access, or billing failed",
            ProviderFailureKind.RATE_LIMIT: "the provider rate limit or quota was reached",
            ProviderFailureKind.NETWORK: "a network failure occurred",
            ProviderFailureKind.SERVICE: "the provider reported service unavailable",
            ProviderFailureKind.REQUEST: "the provider rejected the request",
        }.get(exc.kind, "the provider request failed")
    elif isinstance(exc, SummaryValidationError):
        reason = "the provider returned an invalid structured response"
    elif isinstance(exc, CloudPrivacyError):
        reason = "the provider payload failed local privacy validation"
    else:
        reason = "the compact activity request exceeds the safe request limit"
    metadata = [
        f"daytrace {__version__}",
        f"provider={safe_identifier(provider, '[redacted-provider]')}",
        f"model={safe_identifier(model, '[redacted-model]')}",
    ]
    if isinstance(exc, SummaryValidationError):
        metadata.extend(
            (
                f"code={safe_failure_code(exc.code)}",
                f"field={safe_failure_field(exc.field)}",
            )
        )
        if exc.context is not None:
            metadata.extend(
                (
                    f"stage={exc.context.stage.value}",
                    f"call={exc.context.call_index}",
                )
            )
            if exc.context.response_id:
                metadata.append(
                    "response_id="
                    + safe_identifier(
                        exc.context.response_id, "[redacted-response]"
                    )
                )
            if exc.context.request_id:
                metadata.append(
                    "request_id="
                    + safe_identifier(exc.context.request_id, "[redacted-request]")
                )
    return (
        f"warning: AI summary unavailable because {reason}; "
        f"using deterministic fallback ({'; '.join(metadata)})"
    )


def _failure_details(exc: Exception) -> tuple[str, str | None, object, object]:
    if isinstance(exc, SummaryValidationError):
        return exc.code, exc.field, exc.context, exc.response_shape
    if isinstance(exc, SummaryProviderError):
        kind = exc.kind.value if isinstance(exc.kind, ProviderFailureKind) else "request"
        return f"provider-{kind}", None, None, None
    if isinstance(exc, CloudPrivacyError):
        return "unsafe-cloud-payload", None, None, None
    if isinstance(exc, EpisodeRequestTooLarge):
        return "episode-request-too-large", None, None, None
    if isinstance(exc, MergeRequestTooLarge):
        return "merge-request-too-large", None, None, None
    return "summary-request-too-large", None, None, None


def _write_failure_debug(
    path: Path, exc: Exception, provider: object, model: object
) -> bool:
    code, field, context, response_shape = _failure_details(exc)
    request_id = exc.request_id if isinstance(exc, SummaryProviderError) else None
    rendered = render_summary_failure_json(
        provider=provider,
        model=model,
        code=code,
        field=field,
        context=context,
        response_shape=response_shape,
        request_id=request_id,
    )
    try:
        _write_atomic(path, rendered)
    except OSError:
        print("error: could not write AI failure metadata", file=sys.stderr)
        return False
    return True


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

    if not hasattr(bundle, "episodes"):
        bundle = compact_sessions(bundle)

    if args.diagnostics:
        return 0 if _emit(_render_diagnostics(bundle, args.format), args.output) else 1

    if args.summary == "deterministic":
        return 0 if _emit(_render_deterministic(bundle, args), args.output) else 1

    deterministic_fallback = _render_deterministic(bundle, args)
    try:
        plan = build_summary_plan(bundle)
        if args.debug_output:
            print(
                "AI failure metadata will be written locally if this run fails.",
                file=sys.stderr,
            )
        if not _confirm_cloud_send(plan, args.provider, args.model, args.yes):
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
        digest, provenance = _openai_summary(bundle, api_key, args.model, plan)
        print("AI summary complete; writing output...", file=sys.stderr)
        rendered = (
            render_digest_json(bundle, digest, provenance, details=args.details)
            if args.format == "json"
            else render_digest_markdown(
                bundle, digest, provenance, details=args.details
            )
        )
    except (
        CloudPrivacyError,
        SummaryProviderError,
        SummaryValidationError,
        SummaryRequestTooLarge,
    ) as exc:
        print(_summary_failure_message(exc, args.provider, args.model), file=sys.stderr)
        fallback_written = _emit(deterministic_fallback, args.output)
        debug_written = (
            _write_failure_debug(args.debug_output, exc, args.provider, args.model)
            if args.debug_output
            else True
        )
        return 2 if fallback_written and debug_written else 1

    return 0 if _emit(rendered, args.output) else 1


def entrypoint() -> NoReturn:
    raise SystemExit(main())

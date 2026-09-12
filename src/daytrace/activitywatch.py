from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from datetime import date, timezone

from daytrace.diagnostics import DiagnosticCollector, diagnostic_messages
from daytrace.fusion import fuse_observations
from daytrace.markdown import render_session_markdown
from daytrace.models import DiagnosticCode, SessionBundle
from daytrace.normalize import SUPPORTED_BUCKET_TYPES, normalize_events
from daytrace.sanitize import sanitize_records
from daytrace.sessionize import sessionize
from daytrace.source import ActivitySource, AwClientSource
from daytrace.time import resolve_day
from daytrace.transform import remove_afk


DEFAULT_SERVER = "http://127.0.0.1:5600"


def collect_day(
    day: date,
    *,
    server: str = DEFAULT_SERVER,
    timezone_name: str | None = None,
    source: ActivitySource | None = None,
) -> SessionBundle:
    diagnostics = DiagnosticCollector()
    window = resolve_day(day, timezone_name)
    activity_source = source or AwClientSource.from_url(server)
    activity_source.get_info()
    buckets = activity_source.list_buckets()
    supported = tuple(
        bucket for bucket in buckets if bucket.type in SUPPORTED_BUCKET_TYPES
    )
    unknown_count = len(buckets) - len(supported)
    if unknown_count:
        diagnostics.add(DiagnosticCode.UNSUPPORTED_BUCKET, unknown_count)

    records = tuple(
        record
        for bucket in supported
        for record in normalize_events(
            bucket,
            activity_source.get_events(
                bucket.id,
                window.start.astimezone(timezone.utc),
                window.end.astimezone(timezone.utc),
            ),
            window,
            diagnostics.add,
        )
    )
    active = remove_afk(records)
    sanitized = sanitize_records(active, diagnostics.add)
    slices = fuse_observations(sanitized, diagnostics.add)
    return sessionize(day, window, slices, diagnostics.snapshot())


def summarize_day(
    day: date,
    project: str | None = None,
    *,
    server: str = DEFAULT_SERVER,
    timezone_name: str | None = None,
    source: ActivitySource | None = None,
    warn: Callable[[str], None] | None = None,
) -> str:
    if project is not None:
        warnings.warn(
            "project filtering is deprecated; map workstreams downstream",
            DeprecationWarning,
            stacklevel=2,
        )
    bundle = collect_day(
        day,
        server=server,
        timezone_name=timezone_name,
        source=source,
    )
    warning = warn or logging.getLogger("daytrace").warning
    for message in diagnostic_messages(bundle.diagnostics):
        warning(message)
    return render_session_markdown(bundle)

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timezone

from daytrace.markdown import render_markdown
from daytrace.normalize import SUPPORTED_BUCKET_TYPES, normalize_events
from daytrace.report import build_report
from daytrace.source import ActivitySource, AwClientSource
from daytrace.time import resolve_day
from daytrace.transform import filter_project, merge_adjacent, remove_afk


DEFAULT_SERVER = "http://127.0.0.1:5600"


def summarize_day(
    day: date,
    project: str | None = None,
    *,
    server: str = DEFAULT_SERVER,
    timezone_name: str | None = None,
    source: ActivitySource | None = None,
    warn: Callable[[str], None] | None = None,
) -> str:
    warning = warn or logging.getLogger("daytrace").warning
    window = resolve_day(day, timezone_name)
    activity_source = source or AwClientSource.from_url(server)
    activity_source.get_info()
    buckets = activity_source.list_buckets()
    supported = tuple(
        bucket for bucket in buckets if bucket.type in SUPPORTED_BUCKET_TYPES
    )
    unknown_count = len(buckets) - len(supported)
    if unknown_count:
        noun = "bucket" if unknown_count == 1 else "buckets"
        warning(f"ignored {unknown_count} unsupported ActivityWatch {noun}")

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
            warning,
        )
    )
    transformed = merge_adjacent(filter_project(remove_afk(records), project))
    return render_markdown(build_report(day, window, transformed, project))

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from daytrace.models import (
    ActivityRecord,
    DayWindow,
    DiagnosticCode,
    RawBucket,
    RawEvent,
    SourceKind,
)


ONE_SECOND = timedelta(seconds=1)
SUPPORTED_BUCKET_TYPES: Mapping[str, SourceKind] = {
    "currentwindow": SourceKind.WINDOW,
    "afkstatus": SourceKind.AFK,
    "app.editor.activity": SourceKind.EDITOR,
    "web.tab.current": SourceKind.BROWSER,
}


def _text(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def _url_parts(data: Mapping[str, object]) -> tuple[str | None, str | None]:
    value = _text(data, "url")
    if not value:
        return None, None
    try:
        parsed = urlsplit(value)
        return parsed.hostname.lower() if parsed.hostname else None, parsed.path or None
    except ValueError:
        return None, None


def normalize_events(
    bucket: RawBucket,
    events: Iterable[RawEvent],
    window: DayWindow,
    warn: Callable[[DiagnosticCode], None],
) -> tuple[ActivityRecord, ...]:
    kind = SUPPORTED_BUCKET_TYPES[bucket.type]
    normalized: list[ActivityRecord] = []
    window_start = window.start.astimezone(timezone.utc)
    window_end = window.end.astimezone(timezone.utc)

    for event in events:
        if event.timestamp.tzinfo is None:
            warn(DiagnosticCode.NAIVE_TIMESTAMP)
            continue
        raw_start = event.timestamp.astimezone(timezone.utc)
        start = max(raw_start, window_start)
        end = min(raw_start + event.duration_seconds * ONE_SECOND, window_end)
        if end <= start:
            warn(DiagnosticCode.NON_POSITIVE_EVENT)
            continue
        url_host, url_path = _url_parts(event.data)
        normalized.append(
            ActivityRecord(
                event_id=event.id,
                bucket_id=bucket.id,
                kind=kind,
                start=start,
                end=end,
                app=_text(event.data, "app"),
                title=_text(event.data, "title"),
                project=_text(event.data, "project"),
                file=_text(event.data, "file"),
                url_host=url_host,
                url_path=url_path,
                language=_text(event.data, "language"),
                status=_text(event.data, "status"),
            )
        )

    return tuple(
        sorted(normalized, key=lambda item: (item.start, item.bucket_id, item.event_id))
    )

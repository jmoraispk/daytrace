from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from daytrace.models import ActivityRecord, DayWindow, RawBucket, RawEvent, SourceKind


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


def _url_host(data: Mapping[str, object]) -> str | None:
    value = _text(data, "url")
    if not value:
        return None
    try:
        return urlsplit(value).hostname
    except ValueError:
        return None


def normalize_events(
    bucket: RawBucket,
    events: Iterable[RawEvent],
    window: DayWindow,
    warn: Callable[[str], None],
) -> tuple[ActivityRecord, ...]:
    kind = SUPPORTED_BUCKET_TYPES[bucket.type]
    normalized: list[ActivityRecord] = []
    window_start = window.start.astimezone(timezone.utc)
    window_end = window.end.astimezone(timezone.utc)

    for event in events:
        if event.timestamp.tzinfo is None:
            warn(
                f"skipped naive timestamp for event {event.id!r} in bucket {bucket.id!r}"
            )
            continue
        raw_start = event.timestamp.astimezone(timezone.utc)
        start = max(raw_start, window_start)
        end = min(raw_start + event.duration_seconds * ONE_SECOND, window_end)
        if end <= start:
            warn(f"skipped non-positive event {event.id!r} in bucket {bucket.id!r}")
            continue
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
                url_host=_url_host(event.data),
                language=_text(event.data, "language"),
                status=_text(event.data, "status"),
            )
        )

    return tuple(
        sorted(normalized, key=lambda item: (item.start, item.bucket_id, item.event_id))
    )

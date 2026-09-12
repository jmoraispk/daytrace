from datetime import date, datetime, timezone

from daytrace.diagnostics import DiagnosticCollector
from daytrace.models import DiagnosticCode, DiagnosticCount, RawBucket, RawEvent, SourceKind
from daytrace.normalize import normalize_events
from daytrace.time import resolve_day


def event(
    event_id: str, timestamp: str, seconds: float, data: dict[str, object]
) -> RawEvent:
    return RawEvent(
        id=event_id,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        duration_seconds=seconds,
        data=data,
    )


def test_normalizes_all_supported_watcher_shapes_without_full_url() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    cases = [
        ("currentwindow", {"app": "Code", "title": "daytrace"}, SourceKind.WINDOW),
        ("afkstatus", {"status": "afk"}, SourceKind.AFK),
        (
            "app.editor.activity",
            {
                "file": "C:/src/daytrace/main.py",
                "project": "C:/src/daytrace",
                "language": "Python",
            },
            SourceKind.EDITOR,
        ),
        (
            "web.tab.current",
            {"url": "https://docs.activitywatch.net/api?q=secret", "title": "API docs"},
            SourceKind.BROWSER,
        ),
    ]

    records = []
    for index, (bucket_type, data, expected_kind) in enumerate(cases):
        bucket = RawBucket(str(index), bucket_type, "test", "host")
        record = normalize_events(
            bucket,
            [event(str(index), "2026-09-10T12:00:00Z", 60, data)],
            window,
            lambda message: None,
        )[0]
        assert record.kind is expected_kind
        records.append(record)

    assert records[3].url_host == "docs.activitywatch.net"
    assert "secret" not in repr(records[3])


def test_clips_cross_boundary_drops_zero_length_and_sorts_records() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("window", "currentwindow", "test", "host")
    warnings: list[DiagnosticCode] = []

    records = normalize_events(
        bucket,
        [
            event("later", "2026-09-10T12:00:00Z", 60, {"app": "Code"}),
            event("cross", "2026-09-09T23:59:00Z", 120, {"app": "Code"}),
            event("end", "2026-09-11T00:00:00Z", 0, {"app": "Code"}),
        ],
        window,
        warnings.append,
    )

    assert [
        (record.event_id, record.start, record.duration_seconds) for record in records
    ] == [
        ("cross", datetime(2026, 9, 10, tzinfo=timezone.utc), 60),
        ("later", datetime(2026, 9, 10, 12, tzinfo=timezone.utc), 60),
    ]
    assert warnings == [DiagnosticCode.NON_POSITIVE_EVENT]


def test_skips_naive_timestamp_with_safe_warning() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("window", "currentwindow", "test", "host")
    warnings: list[DiagnosticCode] = []
    naive = RawEvent("naive", datetime(2026, 9, 10, 12), 60, {"app": "Code"})

    assert normalize_events(bucket, (naive,), window, warnings.append) == ()
    assert warnings == [DiagnosticCode.NAIVE_TIMESTAMP]


def test_invalid_browser_url_is_not_retained() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("web", "web.tab.current", "test", "host")
    raw = event(
        "bad-url",
        "2026-09-10T12:00:00Z",
        60,
        {"url": "http://[invalid", "title": "tab"},
    )

    record = normalize_events(bucket, (raw,), window, lambda message: None)[0]

    assert record.url_host is None
    assert "http://[invalid" not in repr(record)


def test_browser_url_keeps_path_but_never_query_or_fragment() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("web", "web.tab.current", "test", "host")
    raw = event(
        "browser-event",
        "2026-09-10T12:00:00Z",
        60,
        {
            "url": "https://github.com/jmoraispk/perflife?code=secret#token",
            "title": "repository",
        },
    )

    record = normalize_events(bucket, (raw,), window, lambda code: None)[0]

    assert record.url_host == "github.com"
    assert record.url_path == "/jmoraispk/perflife"
    assert "code=secret" not in repr(record)
    assert "token" not in repr(record)


def test_non_positive_event_reports_content_free_code() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("private-bucket", "currentwindow", "test", "host")
    diagnostics = DiagnosticCollector()

    records = normalize_events(
        bucket,
        (event("private-event", "2026-09-11T00:00:00Z", 0, {"app": "Code"}),),
        window,
        diagnostics.add,
    )

    assert records == ()
    assert diagnostics.snapshot() == (
        DiagnosticCount(DiagnosticCode.NON_POSITIVE_EVENT, 1),
    )
    assert "private-event" not in repr(diagnostics.snapshot())

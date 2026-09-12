from datetime import date, datetime, timedelta, timezone

from daytrace.activitywatch import collect_day, summarize_day
from daytrace.models import (
    DiagnosticCode,
    DiagnosticCount,
    RawBucket,
    RawEvent,
    ServerInfo,
)


class FakeSource:
    def get_info(self) -> ServerInfo:
        return ServerInfo("v0.13.2 (rust)", True)

    def list_buckets(self) -> tuple[RawBucket, ...]:
        return (
            RawBucket("window", "currentwindow", "watcher", "host"),
            RawBucket("web", "web.tab.current", "watcher", "host"),
            RawBucket("afk", "afkstatus", "watcher", "host"),
            RawBucket("ignored", "custom.private", "watcher", "host"),
        )

    def get_events(self, bucket_id, start, end) -> tuple[RawEvent, ...]:
        at_nine = datetime(2026, 9, 10, 9, tzinfo=timezone.utc)
        return {
            "window": (
                RawEvent(
                    "w1",
                    at_nine,
                    600,
                    {"app": "msedge.exe", "title": "PerfLife"},
                ),
                RawEvent("w0", at_nine, 0, {"app": "msedge.exe"}),
            ),
            "web": (
                RawEvent(
                    "b1",
                    at_nine,
                    600,
                    {
                        "url": "https://github.com/jmoraispk/perflife?token=secret",
                        "title": "jmoraispk/perflife",
                    },
                ),
                RawEvent(
                    "b0",
                    at_nine,
                    0,
                    {"url": "https://example.test/?secret=yes"},
                ),
            ),
            "afk": (
                RawEvent(
                    "a1",
                    at_nine + timedelta(minutes=5),
                    120,
                    {"status": "afk"},
                ),
            ),
        }[bucket_id]


def test_collect_day_runs_sanitized_session_pipeline() -> None:
    bundle = collect_day(
        date(2026, 9, 10), timezone_name="UTC", source=FakeSource()
    )

    assert bundle.focused_seconds == 480
    assert len(bundle.sessions) == 1
    assert bundle.sessions[0].label == "jmoraispk/perflife"
    assert bundle.diagnostics == (
        DiagnosticCount(DiagnosticCode.NON_POSITIVE_EVENT, 2),
        DiagnosticCount(DiagnosticCode.UNSUPPORTED_BUCKET, 1),
    )
    assert "secret" not in repr(bundle)


def test_summarize_day_keeps_deterministic_compatibility_api() -> None:
    warnings: list[str] = []

    markdown = summarize_day(
        date(2026, 9, 10),
        timezone_name="UTC",
        source=FakeSource(),
        warn=warnings.append,
    )

    assert "Summary: Deterministic activity sessions" in markdown
    assert "09:00–09:10" in markdown
    assert "(8m)" in markdown
    assert warnings == [
        "ignored 2 non-positive ActivityWatch events",
        "ignored 1 unsupported ActivityWatch bucket",
    ]

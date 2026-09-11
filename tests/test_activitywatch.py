from datetime import date, datetime, timezone

from daytrace.activitywatch import summarize_day
from daytrace.models import RawBucket, RawEvent, ServerInfo


class FakeSource:
    def get_info(self) -> ServerInfo:
        return ServerInfo("v0.13.2 (rust)", True)

    def list_buckets(self) -> tuple[RawBucket, ...]:
        return (
            RawBucket("window", "currentwindow", "watcher", "host"),
            RawBucket("afk", "afkstatus", "watcher", "host"),
            RawBucket("ignored", "custom.private", "watcher", "host"),
        )

    def get_events(self, bucket_id, start, end) -> tuple[RawEvent, ...]:
        data = {
            "window": (
                RawEvent(
                    "1",
                    datetime(2026, 9, 10, 9, tzinfo=timezone.utc),
                    600,
                    {"app": "Code", "title": "daytrace"},
                ),
            ),
            "afk": (
                RawEvent(
                    "2",
                    datetime(2026, 9, 10, 9, 5, tzinfo=timezone.utc),
                    120,
                    {"status": "afk"},
                ),
            ),
        }
        return data[bucket_id]


def test_summarize_day_runs_the_complete_pipeline() -> None:
    warnings: list[str] = []

    markdown = summarize_day(
        date(2026, 9, 10),
        "daytrace",
        timezone_name="UTC",
        source=FakeSource(),
        warn=warnings.append,
    )

    assert "Active matched time: 8m" in markdown
    assert "09:00–09:05" in markdown
    assert "09:07–09:10" in markdown
    assert warnings == ["ignored 1 unsupported ActivityWatch bucket"]

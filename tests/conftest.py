from datetime import datetime, timedelta, timezone

import pytest

from daytrace.models import ActivityRecord, SourceKind


@pytest.fixture
def make_record():
    def factory(
        start_minute: int,
        duration_minutes: int,
        *,
        kind: SourceKind = SourceKind.WINDOW,
        bucket: str = "window",
        event_id: str = "1",
        app: str | None = "Code",
        title: str | None = "daytrace",
        project: str | None = None,
        file: str | None = None,
        url_host: str | None = None,
        url_path: str | None = None,
        language: str | None = None,
        status: str | None = None,
    ) -> ActivityRecord:
        start = datetime(2026, 9, 10, 9, tzinfo=timezone.utc) + timedelta(
            minutes=start_minute
        )
        return ActivityRecord(
            event_id=event_id,
            bucket_id=bucket,
            kind=kind,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            app=app,
            title=title,
            project=project,
            file=file,
            url_host=url_host,
            url_path=url_path,
            language=language,
            status=status,
        )

    return factory

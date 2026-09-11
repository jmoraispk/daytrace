from collections import defaultdict
from datetime import date

from daytrace.models import (
    ActivityRecord,
    ActivityReport,
    ApplicationTotal,
    DayWindow,
    SourceKind,
)
from daytrace.transform import partition_window_seconds


SOURCE_ORDER = {
    SourceKind.WINDOW: 0,
    SourceKind.EDITOR: 1,
    SourceKind.BROWSER: 2,
}


def build_report(
    day: date,
    window: DayWindow,
    records: tuple[ActivityRecord, ...],
    project: str | None,
) -> ActivityReport:
    timeline = tuple(
        sorted(records, key=lambda item: (item.start, item.bucket_id, item.event_id))
    )
    allocation = partition_window_seconds(timeline)
    app_seconds: dict[str, float] = defaultdict(float)
    for record, seconds in allocation:
        app_seconds[record.app or "Unknown application"] += seconds
    applications = tuple(
        ApplicationTotal(app, seconds)
        for app, seconds in sorted(
            app_seconds.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
        )
    )
    sources = tuple(sorted({item.kind for item in timeline}, key=SOURCE_ORDER.__getitem__))
    return ActivityReport(
        day=day,
        timezone_name=window.timezone_name,
        project=project,
        active_seconds=sum(item.seconds for item in applications) if allocation else None,
        sources=sources,
        timeline=timeline,
        applications=applications,
    )

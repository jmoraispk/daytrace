from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timedelta

from daytrace.models import ActivityRecord, SourceKind


def _sort(records: Iterable[ActivityRecord]) -> tuple[ActivityRecord, ...]:
    return tuple(
        sorted(records, key=lambda item: (item.start, item.bucket_id, item.event_id))
    )


def _union(
    intervals: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _subtract_interval(
    fragments: list[tuple[datetime, datetime]],
    away_start: datetime,
    away_end: datetime,
) -> list[tuple[datetime, datetime]]:
    output: list[tuple[datetime, datetime]] = []
    for start, end in fragments:
        if away_end <= start or away_start >= end:
            output.append((start, end))
            continue
        if start < away_start:
            output.append((start, away_start))
        if away_end < end:
            output.append((away_end, end))
    return output


def remove_afk(records: Iterable[ActivityRecord]) -> tuple[ActivityRecord, ...]:
    items = tuple(records)
    away = _union(
        (item.start, item.end)
        for item in items
        if item.kind is SourceKind.AFK and (item.status or "").casefold() == "afk"
    )
    output: list[ActivityRecord] = []
    for item in items:
        if item.kind is SourceKind.AFK:
            continue
        fragments = [(item.start, item.end)]
        for away_start, away_end in away:
            fragments = _subtract_interval(fragments, away_start, away_end)
        output.extend(replace(item, start=start, end=end) for start, end in fragments)
    return _sort(output)


def filter_project(
    records: Iterable[ActivityRecord], project: str | None
) -> tuple[ActivityRecord, ...]:
    if project is None:
        return _sort(records)
    needle = project.casefold()
    return _sort(
        item
        for item in records
        if any(
            needle in value.casefold()
            for value in (
                item.project,
                item.app,
                item.title,
                item.file,
                item.url_host,
                item.bucket_id,
            )
            if value
        )
    )


def merge_adjacent(
    records: Iterable[ActivityRecord],
    maximum_gap: timedelta = timedelta(seconds=60),
) -> tuple[ActivityRecord, ...]:
    by_bucket: dict[str, list[ActivityRecord]] = defaultdict(list)
    for item in _sort(records):
        bucket_records = by_bucket[item.bucket_id]
        if (
            bucket_records
            and bucket_records[-1].content_key() == item.content_key()
            and item.start - bucket_records[-1].end <= maximum_gap
        ):
            bucket_records[-1] = replace(
                bucket_records[-1], end=max(bucket_records[-1].end, item.end)
            )
        else:
            bucket_records.append(item)
    return _sort(
        item for bucket_records in by_bucket.values() for item in bucket_records
    )


def partition_window_seconds(
    records: Iterable[ActivityRecord],
) -> tuple[tuple[ActivityRecord, float], ...]:
    windows = tuple(item for item in records if item.kind is SourceKind.WINDOW)
    boundaries = sorted({point for item in windows for point in (item.start, item.end)})
    totals: dict[ActivityRecord, float] = defaultdict(float)
    for start, end in zip(boundaries, boundaries[1:]):
        candidates = [item for item in windows if item.start < end and item.end > start]
        if candidates:
            winner = min(candidates, key=lambda item: (item.bucket_id, item.event_id))
            totals[winner] += (end - start).total_seconds()
    return tuple(
        sorted(totals.items(), key=lambda pair: (pair[0].bucket_id, pair[0].event_id))
    )

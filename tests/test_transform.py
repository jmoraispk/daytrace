from dataclasses import replace
from datetime import timedelta

import pytest

from daytrace.models import SourceKind
from daytrace.transform import (
    filter_project,
    merge_adjacent,
    partition_window_seconds,
    remove_afk,
)


def test_remove_afk_splits_active_record(make_record) -> None:
    window = make_record(0, 30)
    away = make_record(10, 5, kind=SourceKind.AFK, bucket="afk", status="afk")

    result = remove_afk((window, away))

    assert [(item.start.minute, item.end.minute) for item in result] == [(0, 10), (15, 30)]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project", "C:/Work/DAYTRACE"),
        ("app", "DAYTRACE Editor"),
        ("title", "Résumé DAYTRACE"),
        ("file", "C:/Work/DAYTRACE/main.py"),
        ("url_host", "DAYTRACE.example"),
        ("bucket_id", "DAYTRACE-window"),
    ],
)
def test_filter_project_uses_unicode_casefold_across_fields(
    make_record, field: str, value: str
) -> None:
    matching = replace(make_record(0, 5, title="unrelated"), **{field: value})
    other = make_record(5, 5, title="mail", project="C:/Personal", event_id="2")

    assert filter_project((matching, other), "daytrace") == (matching,)


def test_merge_adjacent_requires_same_bucket_and_content(make_record) -> None:
    first = make_record(0, 5, event_id="1")
    second = make_record(6, 5, event_id="2")
    other_bucket = make_record(12, 5, event_id="3", bucket="window-2")

    result = merge_adjacent((first, second, other_bucket), timedelta(seconds=60))

    assert [(item.bucket_id, item.start.minute, item.end.minute) for item in result] == [
        ("window", 0, 11),
        ("window-2", 12, 17),
    ]


def test_merge_adjacent_tracks_each_bucket_independently(make_record) -> None:
    first = make_record(0, 5, event_id="1")
    interleaved = make_record(5, 1, event_id="2", bucket="editor", kind=SourceKind.EDITOR)
    second = make_record(6, 5, event_id="3")

    result = merge_adjacent((first, interleaved, second), timedelta(seconds=60))

    assert [(item.bucket_id, item.start.minute, item.end.minute) for item in result] == [
        ("window", 0, 11),
        ("editor", 5, 6),
    ]


def test_partition_window_seconds_never_double_counts(make_record) -> None:
    later_bucket = make_record(0, 20, bucket="z-window", app="Firefox")
    first_bucket = make_record(10, 20, bucket="a-window", app="Code")

    allocation = partition_window_seconds((later_bucket, first_bucket))
    totals = {record.app: seconds for record, seconds in allocation}

    assert totals == {"Code": 1200, "Firefox": 600}
    assert sum(totals.values()) == 1800


def test_not_afk_does_not_remove_time(make_record) -> None:
    window = make_record(0, 10)
    active = make_record(0, 10, kind=SourceKind.AFK, bucket="afk", status="not-afk")
    assert remove_afk((window, active)) == (window,)


def test_afk_covering_record_removes_it(make_record) -> None:
    window = make_record(5, 5)
    away = make_record(0, 20, kind=SourceKind.AFK, bucket="afk", status="afk")
    assert remove_afk((window, away)) == ()


def test_empty_project_matches_every_record(make_record) -> None:
    records = (make_record(0, 5), make_record(5, 5, event_id="2"))
    assert filter_project(records, "") == records


def test_partition_ignores_non_window_sources(make_record) -> None:
    editor = make_record(0, 30, kind=SourceKind.EDITOR, bucket="editor")
    browser = make_record(0, 30, kind=SourceKind.BROWSER, bucket="web")
    assert partition_window_seconds((editor, browser)) == ()


def test_touching_afk_intervals_are_unioned(make_record) -> None:
    window = make_record(0, 30)
    first = make_record(5, 5, kind=SourceKind.AFK, bucket="afk", status="afk")
    second = make_record(
        10, 5, kind=SourceKind.AFK, bucket="afk", event_id="2", status="afk"
    )
    result = remove_afk((window, first, second))
    assert [(item.start.minute, item.end.minute) for item in result] == [(0, 5), (15, 30)]


def test_overlapping_identical_records_merge_to_later_end(make_record) -> None:
    first = make_record(0, 10, event_id="1")
    second = make_record(5, 10, event_id="2")
    result = merge_adjacent((first, second))
    assert [(item.start.minute, item.end.minute) for item in result] == [(0, 15)]

from dataclasses import replace
from datetime import date
from pathlib import Path

from daytrace.markdown import (
    format_duration,
    render_digest_markdown,
    render_markdown,
    render_session_markdown,
)
from daytrace.models import SourceKind
from daytrace.report import build_report
from daytrace.time import resolve_day


def test_render_markdown_matches_golden_file(make_record) -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    window_record = make_record(2, 25, title="daytrace: ActivityWatch client")
    browser_record = replace(
        make_record(
            28,
            13,
            kind=SourceKind.BROWSER,
            bucket="web",
            event_id="2",
            app=None,
            title="ActivityWatch REST API",
        ),
        url_host="docs.activitywatch.net",
    )

    markdown = render_markdown(
        build_report(
            date(2026, 9, 10), window, (window_record, browser_record), "daytrace"
        )
    )

    expected = Path("tests/golden/daytrace-2026-09-10.md").read_text(encoding="utf-8")
    assert markdown == expected
    assert markdown.endswith("\n")
    assert "http" not in markdown


def test_duration_does_not_inflate_short_activity() -> None:
    assert format_duration(1) == "<1m"
    assert format_duration(59.9) == "<1m"
    assert format_duration(60) == "1m"
    assert format_duration(89) == "1m"
    assert format_duration(90) == "2m"
    assert format_duration(3600) == "1h"


def test_render_session_markdown_matches_golden(make_bundle) -> None:
    rendered = render_session_markdown(make_bundle())
    expected = Path("tests/golden/daytrace-sessions-2026-09-10.md").read_text(
        encoding="utf-8"
    )
    assert rendered == expected
    assert "Project filter" not in rendered
    assert "?" not in rendered


def test_render_workstream_digest_matches_golden(
    make_bundle, make_digest, make_provenance
) -> None:
    rendered = render_digest_markdown(
        make_bundle(), make_digest(), make_provenance()
    )
    expected = Path("tests/golden/daytrace-workstreams-2026-09-10.md").read_text(
        encoding="utf-8"
    )
    assert rendered == expected
    assert "## PerfLife" in rendered
    assert "### Apparent achievements" in rendered
    assert "### Work and topics" in rendered
    assert "### Activity" in rendered
    assert "Inferred workstream" in rendered


def test_empty_report_is_valid_markdown() -> None:
    report = build_report(
        date(2026, 9, 10), resolve_day(date(2026, 9, 10), "UTC"), (), None
    )
    assert render_markdown(report).endswith("No matching activity.\n")


def test_non_window_report_marks_active_time_unavailable(make_record) -> None:
    editor = make_record(0, 5, kind=SourceKind.EDITOR, bucket="editor")
    report = build_report(
        date(2026, 9, 10), resolve_day(date(2026, 9, 10), "UTC"), (editor,), None
    )
    assert report.active_seconds is None
    assert report.applications == ()
    assert "Active matched time: Unavailable" in render_markdown(report)


def test_renderer_escapes_markup_and_uses_report_timezone(make_record) -> None:
    record = make_record(7 * 60, 5, title="<script>\n*secret*")
    report = build_report(
        date(2026, 9, 10),
        resolve_day(date(2026, 9, 10), "America/Los_Angeles"),
        (record,),
        None,
    )
    rendered = render_markdown(report)
    assert "<script>" not in rendered
    assert "09:00–09:05" in rendered
    assert rendered == render_markdown(report)

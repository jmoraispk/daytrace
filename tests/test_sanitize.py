from dataclasses import replace

from daytrace.diagnostics import DiagnosticCollector
from daytrace.models import SourceKind
from daytrace.sanitize import sanitize_records


def test_sanitizes_url_like_title_tokens_email_and_edge_suffix(make_record) -> None:
    records = (
        replace(
            make_record(0, 1, kind=SourceKind.BROWSER, bucket="web"),
            title="https://login.example/callback?code=oauth-secret#state",
            url_host="login.example",
            url_path="/callback",
        ),
        replace(
            make_record(1, 1, event_id="2"),
            title="Inbox - joaom@example.com - Outlook",
        ),
        replace(
            make_record(2, 1, event_id="3"),
            title="PerfLife and 45 more pages - Work - Microsoft Edge",
        ),
    )
    diagnostics = DiagnosticCollector()

    sanitized = sanitize_records(records, diagnostics.add)

    assert sanitized[0].title == "login.example"
    assert sanitized[0].url_path is None
    assert sanitized[1].title == "Inbox - [redacted-email] - Outlook"
    assert sanitized[2].title == "PerfLife"
    assert "oauth-secret" not in repr(sanitized)
    assert diagnostics.snapshot()


def test_retains_bounded_repository_and_merge_request_paths(make_record) -> None:
    records = (
        replace(
            make_record(0, 1, kind=SourceKind.BROWSER, bucket="web"),
            url_host="github.com",
            url_path="/jmoraispk/perflife/issues/123/private",
        ),
        replace(
            make_record(1, 1, kind=SourceKind.BROWSER, bucket="web", event_id="2"),
            url_host="gitlab-master.nvidia.com",
            url_path="/gputelecom/aerial-sls/-/merge_requests/155/diffs",
        ),
    )

    sanitized = sanitize_records(records, lambda code: None)

    assert sanitized[0].url_path == "/jmoraispk/perflife"
    assert sanitized[1].url_path == "/gputelecom/aerial-sls/-/merge_requests/155"

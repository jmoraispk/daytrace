from dataclasses import replace

import pytest

from daytrace.diagnostics import DiagnosticCollector
from daytrace.models import SourceKind
from daytrace.sanitize import sanitize_generated_text, sanitize_records


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


def test_generated_text_gets_a_second_secret_scan() -> None:
    assert sanitize_generated_text("token=abcdefghijklmnop") == "[redacted-secret]"


@pytest.mark.parametrize(
    "value",
    (
        "code_challenge=abcdefghijklmnop",
        "session_state=abcdefghijklmnop",
        "api_key=abcdefghijklmnop",
    ),
)
def test_generated_text_scans_common_credential_fields(value: str) -> None:
    assert sanitize_generated_text(value) == "[redacted-secret]"


def test_editor_paths_are_minimized_before_leaving_sanitizer(make_record) -> None:
    record = make_record(
        0,
        5,
        kind=SourceKind.EDITOR,
        project="C:/Users/joaom/private/daytrace",
        file="C:/Users/joaom/private/daytrace/main.py",
    )

    sanitized = sanitize_records((record,), lambda code: None)

    assert sanitized[0].project == "daytrace"
    assert sanitized[0].file == "main.py"
    assert "Users" not in repr(sanitized)


def test_local_sanitizer_removes_query_from_scheme_less_url_title(make_record) -> None:
    record = make_record(
        0,
        1,
        title="git.example/oauth/authorize?client_id=public&state=private",
    )

    sanitized = sanitize_records((record,), lambda code: None)

    assert sanitized[0].title == "git.example"

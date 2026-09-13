import pytest

from daytrace.cloud_privacy import (
    minimize_cloud_path,
    minimize_cloud_text,
    minimize_cloud_title,
)


def test_cloud_title_removes_embedded_url_query_and_fragment() -> None:
    title = "Authorize https://auth.example/oauth?client_id=abc&state=secret#done"
    assert minimize_cloud_title("Edge", title) == "Authorize auth.example"


def test_cloud_title_removes_direct_message_participant() -> None:
    assert (
        minimize_cloud_title("Slack", "Example Person (DM) - Company - Slack")
        == "Direct message - Slack"
    )


def test_cloud_title_drops_unstructured_meeting_topic() -> None:
    title = "Scheduler requirements | Company | person@example.com | Microsoft Teams"
    assert minimize_cloud_title("Teams", title) == "Meeting - Microsoft Teams"


def test_cloud_title_drops_mail_participant_without_application_hint() -> None:
    assert (
        minimize_cloud_title(None, "Inbox - Example Person - Outlook")
        == "Inbox - Outlook"
    )


def test_cloud_path_keeps_only_basename() -> None:
    assert minimize_cloud_path(r"C:\Users\person\private\report.pdf") == "report.pdf"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Visit 127.0.0.1:8765/?key=" + "a" * 40, "Visit 127.0.0.1"),
        ("localhost:5173/#token=" + "b" * 40, "localhost"),
        ("https://user:pass@example.test:9443/a?q=x#f", "example.test"),
    ],
)
def test_cloud_text_structurally_removes_url_private_parts(
    value: str, expected: str
) -> None:
    assert minimize_cloud_text(value) == expected

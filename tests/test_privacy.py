from datetime import date, datetime, timezone
from dataclasses import replace
import json

import pytest

from daytrace.activitywatch import collect_day
from daytrace.json_output import render_digest_json, render_episode_json
from daytrace.markdown import render_digest_markdown, render_episode_markdown
from daytrace.models import ProviderResponse, RawBucket, RawEvent, ServerInfo
from daytrace.summarize import build_summary_request, summarize_bundle


SENSITIVE = (
    "oauth-secret",
    "code_challenge=",
    "session_state=",
    "api_key=",
    "joaom@example.com",
)


class SensitiveSource:
    def get_info(self):
        return ServerInfo("test", True)

    def list_buckets(self):
        return (
            RawBucket("window-private", "currentwindow", "test", "host"),
            RawBucket("browser-private", "web.tab.current", "test", "host"),
        )

    def get_events(self, bucket_id, start, end):
        if bucket_id == "window-private":
            return (
                RawEvent(
                    "event-private",
                    datetime(2026, 9, 10, 9, tzinfo=timezone.utc),
                    300,
                    {
                        "app": "msedge.exe",
                        "title": "Inbox - joaom@example.com - Outlook",
                    },
                ),
            )
        return (
            RawEvent(
                "browser-event-private",
                datetime(2026, 9, 10, 9, tzinfo=timezone.utc),
                300,
                {
                    "url": "https://accounts.example/callback?code=oauth-secret&code_challenge=value&session_state=value&api_key=value",
                    "title": "https://accounts.example/callback?code=oauth-secret",
                },
            ),
        )


class RecordingProvider:
    def __init__(self):
        self.requests = []

    def summarize(self, request):
        self.requests.append(request)
        episode_ids = [item["id"] for item in request.payload["episodes"]]
        return ProviderResponse(
            payload={
                "schema": "daytrace.workstream-digest.v2",
                "workstreams": [],
                "unassigned_episode_ids": episode_ids,
            },
            provider="privacy-test",
            model="fixed",
        )


@pytest.fixture
def sensitive_source():
    return SensitiveSource()


@pytest.fixture
def recording_provider():
    return RecordingProvider()


def test_sensitive_trace_shapes_never_reach_bundle_provider_or_outputs(
    sensitive_source, recording_provider
) -> None:
    bundle = collect_day(
        date(2026, 9, 10), timezone_name="UTC", source=sensitive_source
    )
    request = build_summary_request(bundle)
    digest, provenance = summarize_bundle(bundle, recording_provider)
    outputs = (
        repr(bundle),
        json.dumps(request.payload),
        render_episode_markdown(bundle),
        render_episode_markdown(bundle, details=True),
        render_episode_markdown(bundle, raw=True),
        render_episode_json(bundle, details=True),
        render_digest_markdown(bundle, digest, provenance),
        render_digest_json(bundle, digest, provenance, details=True),
        json.dumps(recording_provider.requests[0].payload),
    )
    assert all(secret not in output for secret in SENSITIVE for output in outputs)


def test_cloud_episode_label_removes_direct_message_participant(
    make_episode, make_episode_bundle
) -> None:
    private_name = "Example Person"
    episode = replace(
        make_episode(),
        label=f"{private_name} (DM) - Company - Slack",
        activity_labels=(
            replace(
                make_episode().activity_labels[0],
                value=f"{private_name} (DM) - Company - Slack",
            ),
        ),
    )

    request = build_summary_request(make_episode_bundle((episode,)))
    rendered = json.dumps(request.payload)

    assert private_name not in rendered
    assert "Direct message - Slack" in rendered

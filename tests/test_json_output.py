import json

from daytrace.json_output import (
    render_digest_json,
    render_episode_json,
    render_session_json,
)


def test_episode_json_uses_new_schema(make_episode_bundle) -> None:
    payload = json.loads(render_episode_json(make_episode_bundle()))
    assert payload["schema"] == "daytrace.episode-bundle.v1"
    assert payload["episodes"][0]["id"] == "episode-001"
    assert "sessions" not in payload


def test_raw_episode_json_retains_fine_grained_sessions(make_episode_bundle) -> None:
    payload = json.loads(render_episode_json(make_episode_bundle(), raw=True))
    assert payload["sessions"][0]["id"] == "session-001"


def test_session_json_is_versioned_stable_and_private(make_bundle) -> None:
    rendered = render_session_json(make_bundle(), details=True)
    payload = json.loads(rendered)

    assert payload["schema"] == "daytrace.session-bundle.v1"
    assert payload["sessions"][0]["id"] == "session-001"
    assert payload["sessions"][0]["label"] == "jmoraispk/perflife"
    assert rendered.endswith("\n")
    assert "bucket_id" not in rendered
    assert "event_id" not in rendered
    assert "oauth-secret" not in rendered


def test_digest_json_contains_provenance_and_structured_workstreams(
    make_bundle, make_digest, make_provenance
) -> None:
    rendered = render_digest_json(make_bundle(), make_digest(), make_provenance())
    payload = json.loads(rendered)
    assert payload["schema"] == "daytrace.workstream-report.v1"
    assert payload["summary"]["provider"] == "openai"
    assert payload["workstreams"][0]["session_ids"] == ["session-001"]
    assert "api_key" not in rendered

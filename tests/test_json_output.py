import json

from daytrace.json_output import render_digest_json, render_session_json


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

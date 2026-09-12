import json

from daytrace.json_output import render_session_json


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

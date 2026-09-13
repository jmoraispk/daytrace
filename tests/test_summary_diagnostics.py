import importlib
import json

from daytrace import __version__
from daytrace.models import SummaryFailureContext, SummaryPass


def test_safe_response_shape_omits_generated_prose_and_unknown_ids() -> None:
    diagnostics = importlib.import_module("daytrace.summary_diagnostics")
    payload = {
        "schema": "daytrace.workstream-digest.v2",
        "workstreams": [
            {
                "label": "private generated label",
                "confidence": "high",
                "episode_ids": ["episode-001", "credential-shaped-unknown-id"],
                "topics": [
                    {
                        "text": "private generated topic",
                        "evidence": ["episode-001", "episode-001"],
                    }
                ],
                "outcomes": [
                    {
                        "text": "private generated outcome",
                        "strength": "likely",
                        "evidence": ["credential-shaped-unknown-id"],
                    }
                ],
            }
        ],
        "unassigned_episode_ids": ["episode-002"],
    }

    shape = diagnostics.safe_response_shape(
        payload, {"episode-001", "episode-002"}
    )
    rendered = json.dumps(shape)

    assert shape["workstream_count"] == 1
    assert shape["topic_count"] == 1
    assert shape["outcome_count"] == 1
    assert shape["known_allocated_ids"] == ["episode-001"]
    assert shape["known_unassigned_ids"] == ["episode-002"]
    assert shape["unknown_id_count"] == 2
    assert shape["duplicate_id_count"] == 1
    assert "private generated" not in rendered
    assert "credential-shaped-unknown-id" not in rendered


def test_support_json_uses_allowlisted_failure_fields_only() -> None:
    diagnostics = importlib.import_module("daytrace.summary_diagnostics")
    context = SummaryFailureContext(
        provider="openai",
        model="user-model",
        stage=SummaryPass.CHUNK,
        call_index=1,
        request_character_count=1234,
        item_ids=("episode-001", "episode-002"),
        response_id="resp_test",
        request_id="req_test",
    )

    rendered = diagnostics.render_summary_failure_json(
        provider="openai",
        model="user-model",
        code="unknown-ids",
        field="workstreams[0].episode_ids",
        context=context,
        response_shape={"unknown_id_count": 1},
    )
    payload = json.loads(rendered)

    assert payload == {
        "schema": "daytrace.ai-failure.v1",
        "daytrace_version": __version__,
        "provider": "openai",
        "model": "user-model",
        "stage": "chunk",
        "call_index": 1,
        "request_character_count": 1234,
        "item_count": 2,
        "item_ids": ["episode-001", "episode-002"],
        "response_id": "resp_test",
        "request_id": "req_test",
        "validation": {
            "code": "unknown-ids",
            "field": "workstreams[0].episode_ids",
        },
        "response_shape": {"unknown_id_count": 1},
    }


def test_support_json_redacts_unsafe_identifiers() -> None:
    diagnostics = importlib.import_module("daytrace.summary_diagnostics")

    rendered = diagnostics.render_summary_failure_json(
        provider="openai",
        model="model\nprivate",
        code="unsafe\ncode",
    )

    assert "private" not in rendered
    assert "unsafe\\ncode" not in rendered
    assert json.loads(rendered)["model"] == "[redacted-model]"


def test_provider_failure_support_json_keeps_only_safe_request_id() -> None:
    diagnostics = importlib.import_module("daytrace.summary_diagnostics")

    rendered = diagnostics.render_summary_failure_json(
        provider="openai",
        model="user-model",
        code="provider-network",
        request_id="req_test",
    )

    payload = json.loads(rendered)
    assert payload["request_id"] == "req_test"
    assert "response_id" not in payload

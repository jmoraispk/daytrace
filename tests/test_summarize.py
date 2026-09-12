import json

import pytest

from daytrace.models import Confidence, OutcomeStrength, ProviderResponse
from daytrace.summarize import (
    PROMPT_SCHEMA,
    SummaryValidationError,
    build_summary_plan,
    build_summary_request,
    summarize_bundle,
    validate_digest,
)


def test_summary_plan_contains_minimized_episodes(make_episode_bundle) -> None:
    plan = build_summary_plan(make_episode_bundle())
    request = plan.requests[0]
    rendered = json.dumps(request.payload)

    assert request.schema == "daytrace.summary-request.v2"
    assert request.episode_ids == ("episode-001",)
    assert "episodes" in request.payload
    assert "sessions" not in request.payload
    assert "event_id" not in rendered
    assert "bucket_id" not in rendered
    assert plan.planned_request_count == 1


def test_summary_request_contains_episodes_but_no_private_source_ids(
    make_episode_bundle,
) -> None:
    request = build_summary_request(make_episode_bundle())

    assert request.schema == "daytrace.summary-request.v2"
    assert request.episode_ids == ("episode-001",)
    assert request.character_count == len(
        json.dumps(request.payload, ensure_ascii=False, sort_keys=True)
    )
    rendered = json.dumps(request.payload)
    assert "episode-001" in rendered
    assert "bucket_id" not in rendered
    assert "event_id" not in rendered
    assert request.data_categories == ("anchor", "application", "activity-label")


def valid_payload():
    return {
        "schema": "daytrace.workstream-digest.v2",
        "workstreams": [
            {
                "label": "PerfLife",
                "confidence": "high",
                "episode_ids": ["episode-001"],
                "topics": [
                    {
                        "text": "Defined a health dashboard",
                        "evidence": ["episode-001"],
                    }
                ],
                "outcomes": [
                    {
                        "text": "Created the named repository",
                        "strength": "observed",
                        "evidence": ["episode-001"],
                    }
                ],
            }
        ],
        "unassigned_episode_ids": [],
    }


def test_validates_typed_digest() -> None:
    digest = validate_digest(valid_payload(), {"episode-001"})
    assert digest.workstreams[0].label == "PerfLife"
    assert digest.workstreams[0].confidence is Confidence.HIGH


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["workstreams"][0].update(confidence="certain"),
        lambda value: value["workstreams"][0]["topics"][0].update(evidence=[]),
        lambda value: value["workstreams"][0]["topics"][0].update(
            evidence=["episode-999"]
        ),
        lambda value: value.update(unassigned_episode_ids=["episode-001"]),
    ],
)
def test_rejects_invalid_or_duplicate_evidence(mutation) -> None:
    payload = valid_payload()
    mutation(payload)
    with pytest.raises(SummaryValidationError):
        validate_digest(payload, {"episode-001"})


def test_omits_none_outcomes_and_returns_provenance(make_episode_bundle) -> None:
    payload = valid_payload()
    payload["workstreams"][0]["outcomes"].append(
        {
            "text": "No supported completion",
            "strength": "none",
            "evidence": ["episode-001"],
        }
    )

    class Provider:
        def summarize(self, request):
            return ProviderResponse(payload, "test", "fixed", 10, 5)

    digest, provenance = summarize_bundle(make_episode_bundle(), Provider())

    assert [item.strength for item in digest.workstreams[0].outcomes] == [
        OutcomeStrength.OBSERVED
    ]
    assert provenance.prompt_schema == PROMPT_SCHEMA
    assert (provenance.input_tokens, provenance.output_tokens) == (10, 5)


def test_validated_digest_contains_only_scanned_generated_text() -> None:
    payload = {
        "schema": "daytrace.workstream-digest.v2",
        "workstreams": [
            {
                "label": "PerfLife",
                "confidence": "high",
                "episode_ids": ["episode-001"],
                "topics": [
                    {
                        "text": "token=abcdefghijklmnop",
                        "evidence": ["episode-001"],
                    }
                ],
                "outcomes": [],
            }
        ],
        "unassigned_episode_ids": [],
    }

    digest = validate_digest(payload, {"episode-001"})

    assert digest.workstreams[0].topics[0].text == "[redacted-secret]"

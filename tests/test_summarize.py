import json

import pytest

from daytrace.models import Confidence, OutcomeStrength, ProviderResponse
from daytrace.summarize import (
    PROMPT_SCHEMA,
    SummaryValidationError,
    build_summary_request,
    summarize_bundle,
    validate_digest,
)


def test_summary_request_contains_sessions_but_no_private_source_ids(make_bundle) -> None:
    request = build_summary_request(make_bundle())

    assert request.schema == "daytrace.summary-request.v1"
    assert request.session_count == 1
    assert request.character_count == len(
        json.dumps(request.payload, ensure_ascii=False, sort_keys=True)
    )
    rendered = json.dumps(request.payload)
    assert "session-001" in rendered
    assert "bucket_id" not in rendered
    assert "event_id" not in rendered
    assert "url" not in rendered.casefold()
    assert request.data_categories == ("application", "repository-path", "title")


def valid_payload():
    return {
        "schema": "daytrace.workstream-digest.v1",
        "workstreams": [
            {
                "label": "PerfLife",
                "confidence": "high",
                "session_ids": ["session-001"],
                "topics": [
                    {
                        "text": "Defined a health dashboard",
                        "evidence": ["session-001"],
                    }
                ],
                "outcomes": [
                    {
                        "text": "Created the named repository",
                        "strength": "observed",
                        "evidence": ["session-001"],
                    }
                ],
            }
        ],
        "unassigned_session_ids": [],
    }


def test_validates_typed_digest(make_bundle) -> None:
    digest = validate_digest(valid_payload(), make_bundle())
    assert digest.workstreams[0].label == "PerfLife"
    assert digest.workstreams[0].confidence is Confidence.HIGH


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["workstreams"][0].update(confidence="certain"),
        lambda value: value["workstreams"][0]["topics"][0].update(evidence=[]),
        lambda value: value["workstreams"][0]["topics"][0].update(
            evidence=["session-999"]
        ),
        lambda value: value.update(unassigned_session_ids=["session-001"]),
    ],
)
def test_rejects_invalid_or_duplicate_evidence(make_bundle, mutation) -> None:
    payload = valid_payload()
    mutation(payload)
    with pytest.raises(SummaryValidationError):
        validate_digest(payload, make_bundle())


def test_omits_none_outcomes_and_returns_provenance(make_bundle) -> None:
    payload = valid_payload()
    payload["workstreams"][0]["outcomes"].append(
        {
            "text": "No supported completion",
            "strength": "none",
            "evidence": ["session-001"],
        }
    )

    class Provider:
        def summarize(self, request):
            return ProviderResponse(payload, "test", "fixed", 10, 5)

    digest, provenance = summarize_bundle(make_bundle(), Provider())

    assert [item.strength for item in digest.workstreams[0].outcomes] == [
        OutcomeStrength.OBSERVED
    ]
    assert provenance.prompt_schema == PROMPT_SCHEMA
    assert (provenance.input_tokens, provenance.output_tokens) == (10, 5)


def test_validated_digest_contains_only_scanned_generated_text(make_bundle) -> None:
    payload = {
        "schema": "daytrace.workstream-digest.v1",
        "workstreams": [
            {
                "label": "PerfLife",
                "confidence": "high",
                "session_ids": ["session-001"],
                "topics": [
                    {
                        "text": "token=abcdefghijklmnop",
                        "evidence": ["session-001"],
                    }
                ],
                "outcomes": [],
            }
        ],
        "unassigned_session_ids": [],
    }

    digest = validate_digest(payload, make_bundle())

    assert digest.workstreams[0].topics[0].text == "[redacted-secret]"

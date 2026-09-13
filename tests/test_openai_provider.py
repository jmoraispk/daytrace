import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

import daytrace.providers.openai as openai_provider
from daytrace.models import ProviderFailureKind
from daytrace.prompts import MERGE_SYSTEM_PROMPT, SYSTEM_PROMPT
from daytrace.providers import OpenAIProvider, SummaryProviderError
from daytrace.summarize import build_merge_request, build_summary_plan


def test_openai_provider_uses_prompts_from_prompt_module() -> None:
    assert openai_provider.SYSTEM_PROMPT is SYSTEM_PROMPT
    assert openai_provider.MERGE_SYSTEM_PROMPT is MERGE_SYSTEM_PROMPT


def test_openai_provider_requests_strict_json_and_converts_usage(
    make_episode_bundle,
) -> None:
    calls = []
    response = SimpleNamespace(
        output_text=json.dumps(
            {
                "schema": "daytrace.workstream-digest.v2",
                "workstreams": [],
                "unassigned_episode_ids": ["episode-001"],
            }
        ),
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
        id="resp_test",
        _request_id="req_test",
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: calls.append(kwargs) or response
        )
    )
    provider = OpenAIProvider("runtime-secret", "user-selected-model", client=client)

    result = provider.summarize(build_summary_plan(make_episode_bundle()).requests[0])

    assert result.provider == "openai"
    assert result.model == "user-selected-model"
    assert result.input_tokens == 120
    assert result.response_id == "resp_test"
    assert result.request_id == "req_test"
    assert calls[0]["model"] == "user-selected-model"
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[0]["text"]["format"]["name"] == "daytrace_workstream_digest_v2"
    assert "exactly once" in calls[0]["instructions"]
    assert "unassigned_episode_ids" in calls[0]["instructions"]
    assert "journal-ready" in calls[0]["instructions"]
    assert "mixed episode" in calls[0]["instructions"]
    assert "short but distinct" in calls[0]["instructions"]
    assert "professional writing" in calls[0]["instructions"]
    assert "minority evidence" in calls[0]["instructions"]
    assert "final coverage scan" in calls[0]["instructions"]
    assert "semantically relevant" in calls[0]["instructions"]
    assert "named project context" in calls[0]["instructions"]
    assert "runtime-secret" not in repr(result)
    assert "runtime-secret" not in repr(calls)


def test_openai_provider_rejects_unsafe_payload_before_client_call(
    make_episode_bundle,
) -> None:
    calls = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs))
    )
    provider = OpenAIProvider("runtime-secret", "model", client=client)
    request = build_summary_plan(make_episode_bundle()).requests[0]
    unsafe = replace(
        request,
        payload={"title": "http://localhost:8000/?key=" + "x" * 40},
    )

    with pytest.raises(RuntimeError, match="unsafe-cloud-payload"):
        provider.summarize(unsafe)

    assert calls == []


def test_provider_wraps_sdk_errors_without_private_content(make_episode_bundle) -> None:
    def fail(**kwargs):
        raise RuntimeError("request contained private captured title")

    client = SimpleNamespace(responses=SimpleNamespace(create=fail))
    provider = OpenAIProvider("runtime-secret", "model", client=client)

    with pytest.raises(
        SummaryProviderError, match="OpenAI summary request failed"
    ) as exc:
        provider.summarize(build_summary_plan(make_episode_bundle()).requests[0])
    assert "private captured title" not in str(exc.value)


def test_openai_provider_uses_constrained_merge_schema(
    make_digest,
) -> None:
    calls = []
    response = SimpleNamespace(
        output_text=json.dumps(
            {
                "schema": "daytrace.workstream-merge.v1",
                "groups": [
                    {
                        "label": "PerfLife",
                        "confidence": "high",
                        "provisional_ids": ["provisional-001-001"],
                    }
                ],
            }
        ),
        usage=None,
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: calls.append(kwargs) or response
        )
    )
    request, _ = build_merge_request((make_digest(),))

    OpenAIProvider("secret", "model", client=client).merge(request)

    assert calls[0]["text"]["format"]["name"] == "daytrace_workstream_merge_v1"


def test_summary_schema_restricts_nonempty_ids_to_request(
    make_episode_bundle,
) -> None:
    request = build_summary_plan(make_episode_bundle()).requests[0]

    schema = openai_provider.workstream_json_format(request.episode_ids)["schema"]
    workstream = schema["properties"]["workstreams"]["items"]
    episode_ids = workstream["properties"]["episode_ids"]
    topic_evidence = workstream["properties"]["topics"]["items"]["properties"][
        "evidence"
    ]
    outcome_evidence = workstream["properties"]["outcomes"]["items"][
        "properties"
    ]["evidence"]
    unassigned = schema["properties"]["unassigned_episode_ids"]

    assert episode_ids["minItems"] == 1
    assert episode_ids["items"]["enum"] == ["episode-001"]
    assert topic_evidence["minItems"] == 1
    assert topic_evidence["items"]["enum"] == ["episode-001"]
    assert outcome_evidence["items"]["enum"] == ["episode-001"]
    assert unassigned["items"]["enum"] == ["episode-001"]


def test_merge_schema_restricts_nonempty_ids_to_request(make_digest) -> None:
    request, _ = build_merge_request((make_digest(),))

    schema = openai_provider.merge_json_format(request.provisional_ids)["schema"]
    provisional_ids = schema["properties"]["groups"]["items"]["properties"][
        "provisional_ids"
    ]

    assert provisional_ids["minItems"] == 1
    assert provisional_ids["items"]["enum"] == ["provisional-001-001"]


def test_empty_id_schemas_require_empty_root_collections() -> None:
    summary = openai_provider.workstream_json_format(())["schema"]["properties"]
    merge = openai_provider.merge_json_format(())["schema"]["properties"]

    assert summary["workstreams"]["maxItems"] == 0
    assert summary["unassigned_episode_ids"]["maxItems"] == 0
    assert "enum" not in summary["unassigned_episode_ids"]["items"]
    assert merge["groups"]["maxItems"] == 0


@pytest.mark.parametrize(
    ("status_code", "error_type", "kind"),
    [
        (401, AuthenticationError, ProviderFailureKind.AUTHENTICATION),
        (429, RateLimitError, ProviderFailureKind.RATE_LIMIT),
        (500, InternalServerError, ProviderFailureKind.SERVICE),
        (400, BadRequestError, ProviderFailureKind.REQUEST),
    ],
)
def test_provider_classifies_status_failure_without_sdk_message(
    status_code, error_type, kind, make_episode_bundle
) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        status_code, request=request, headers={"x-request-id": "req_failure"}
    )
    sdk_error = error_type("private provider detail", response=response, body=None)
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(sdk_error)
        )
    )
    provider = OpenAIProvider("runtime-secret", "model", client=client)

    with pytest.raises(SummaryProviderError) as caught:
        provider.summarize(build_summary_plan(make_episode_bundle()).requests[0])

    assert caught.value.kind is kind
    assert caught.value.request_id == "req_failure"
    assert "private provider detail" not in str(caught.value)
    assert "runtime-secret" not in repr(caught.value)


def test_provider_classifies_connection_failure(make_episode_bundle) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    sdk_error = APIConnectionError(request=request)
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: (_ for _ in ()).throw(sdk_error)
        )
    )
    provider = OpenAIProvider("runtime-secret", "model", client=client)

    with pytest.raises(SummaryProviderError) as caught:
        provider.summarize(build_summary_plan(make_episode_bundle()).requests[0])

    assert caught.value.kind is ProviderFailureKind.NETWORK

import json
from types import SimpleNamespace

import pytest

from daytrace.providers import OpenAIProvider, SummaryProviderError
from daytrace.summarize import build_summary_plan


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
    assert calls[0]["model"] == "user-selected-model"
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[0]["text"]["format"]["name"] == "daytrace_workstream_digest_v2"
    assert "runtime-secret" not in repr(result)
    assert "runtime-secret" not in repr(calls)


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

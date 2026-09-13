import json

import pytest

from daytrace.models import (
    Confidence,
    OutcomeStrength,
    OutcomeSummary,
    ProviderResponse,
    WorkstreamDigest,
    WorkstreamSummary,
)
from daytrace.summarize import (
    PROMPT_SCHEMA,
    SummaryValidationError,
    EpisodeRequestTooLarge,
    MergeRequestTooLarge,
    build_summary_plan,
    build_merge_request,
    assemble_merged_digest,
    validate_merge,
    build_summary_request,
    summarize_bundle,
    validate_digest,
)


def test_large_plan_partitions_only_at_episode_boundaries(
    make_many_episode_bundle,
) -> None:
    bundle = make_many_episode_bundle()
    plan = build_summary_plan(bundle, target_characters=800, max_characters=1000)
    assert len(plan.requests) > 1
    assert plan.planned_request_count == len(plan.requests) + 1
    assert all(request.character_count <= 1000 for request in plan.requests)
    assert [
        episode_id for request in plan.requests for episode_id in request.episode_ids
    ] == [item.episode_id for item in bundle.episodes]


def test_merge_validation_rejects_duplicate_provisional_ids() -> None:
    payload = {
        "schema": "daytrace.workstream-merge.v1",
        "groups": [
            {
                "label": "Work",
                "confidence": "high",
                "provisional_ids": ["provisional-001-001"],
            }
        ],
    }
    groups = validate_merge(payload, {"provisional-001-001"})
    assert groups[0].provisional_ids == ("provisional-001-001",)

    payload["groups"][0]["provisional_ids"].append("provisional-001-001")
    with pytest.raises(SummaryValidationError):
        validate_merge(payload, {"provisional-001-001"})


def test_merge_preserves_ten_ungrouped_workstreams_from_fourteen() -> None:
    provisional = {
        f"provisional-{index:03d}": WorkstreamSummary(
            label=f"Workstream {index}",
            confidence=Confidence.MEDIUM,
            episode_ids=(f"episode-{index:03d}",),
            topics=(),
            outcomes=(),
        )
        for index in range(1, 15)
    }
    payload = {
        "schema": "daytrace.workstream-merge.v1",
        "groups": [
            {
                "label": "Merged 1 and 14",
                "confidence": "high",
                "provisional_ids": ["provisional-001", "provisional-014"],
            },
            {
                "label": "Merged 3 and 4",
                "confidence": "medium",
                "provisional_ids": ["provisional-003", "provisional-004"],
            },
        ],
    }

    groups = validate_merge(payload, set(provisional))
    digest = assemble_merged_digest(groups, provisional, ())

    assert len(digest.workstreams) == 12
    allocated = {
        episode_id
        for stream in digest.workstreams
        for episode_id in stream.episode_ids
    }
    assert allocated == {
        f"episode-{index:03d}" for index in range(1, 15)
    }
    assert {stream.label for stream in digest.workstreams} >= {
        "Merged 1 and 14",
        "Merged 3 and 4",
        "Workstream 2",
        "Workstream 13",
    }
    assert [stream.label for stream in digest.workstreams[:3]] == [
        "Merged 1 and 14",
        "Workstream 2",
        "Merged 3 and 4",
    ]


def test_chunk_merge_copies_outcomes_and_counts_every_request(
    make_many_episode_bundle,
) -> None:
    bundle = make_many_episode_bundle()
    plan = build_summary_plan(bundle, target_characters=800, max_characters=1000)

    class Provider:
        def __init__(self):
            self.calls = []

        def summarize(self, request):
            self.calls.append(request)
            index = len(self.calls)
            return ProviderResponse(
                {
                    "schema": "daytrace.workstream-digest.v2",
                    "workstreams": [
                        {
                            "label": f"Chunk {index}",
                            "confidence": "medium",
                            "episode_ids": list(request.episode_ids),
                            "topics": [],
                            "outcomes": [
                                {
                                    "text": f"Observed state {index}",
                                    "strength": "observed",
                                    "evidence": [request.episode_ids[0]],
                                }
                            ],
                        }
                    ],
                    "unassigned_episode_ids": [],
                },
                "test",
                "fixed",
                10,
                5,
            )

        def merge(self, request):
            self.calls.append(request)
            return ProviderResponse(
                {
                    "schema": "daytrace.workstream-merge.v1",
                    "groups": [
                        {
                            "label": "Combined work",
                            "confidence": "high",
                            "provisional_ids": list(request.provisional_ids),
                        }
                    ],
                },
                "test",
                "fixed",
                7,
                3,
            )

    provider = Provider()
    digest, provenance = summarize_bundle(bundle, provider, plan)

    assert provenance.request_count == len(plan.requests) + 1 == len(provider.calls)
    assert len(digest.workstreams[0].outcomes) == len(plan.requests)
    assert {item.text for item in digest.workstreams[0].outcomes} == {
        f"Observed state {index}" for index in range(1, len(plan.requests) + 1)
    }
    assert provenance.input_tokens == len(plan.requests) * 10 + 7


def test_retries_global_episode_allocation_once(make_many_episode_bundle) -> None:
    bundle = make_many_episode_bundle(2)
    plan = build_summary_plan(bundle)
    episode_ids = plan.requests[0].episode_ids

    class Provider:
        def __init__(self) -> None:
            self.requests = []

        def summarize(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                payload = {
                    "schema": "daytrace.workstream-digest.v2",
                    "workstreams": [
                        {
                            "label": "First",
                            "confidence": "high",
                            "episode_ids": [episode_ids[0]],
                            "topics": [],
                            "outcomes": [],
                        },
                        {
                            "label": "Second",
                            "confidence": "medium",
                            "episode_ids": [episode_ids[0]],
                            "topics": [],
                            "outcomes": [],
                        },
                    ],
                    "unassigned_episode_ids": [episode_ids[1]],
                }
            else:
                assert request.payload["repair_instruction"] == (
                    "Partition every supplied episode ID exactly once across "
                    "workstreams[].episode_ids and unassigned_episode_ids."
                )
                payload = {
                    "schema": "daytrace.workstream-digest.v2",
                    "workstreams": [
                        {
                            "label": "Work",
                            "confidence": "high",
                            "episode_ids": list(episode_ids),
                            "topics": [],
                            "outcomes": [],
                        }
                    ],
                    "unassigned_episode_ids": [],
                }
            return ProviderResponse(payload, "test", "fixed", 10, 5)

        def merge(self, request):
            raise AssertionError("merge must not be called")

    provider = Provider()

    digest, provenance = summarize_bundle(bundle, provider, plan)

    assert len(provider.requests) == 2
    assert digest.workstreams[0].episode_ids == episode_ids
    assert provenance.request_count == 2
    assert provenance.input_tokens == 20


def test_allocation_repair_is_attempted_only_once(make_many_episode_bundle) -> None:
    bundle = make_many_episode_bundle(2)
    plan = build_summary_plan(bundle)
    episode_ids = plan.requests[0].episode_ids

    class Provider:
        def __init__(self) -> None:
            self.requests = []

        def summarize(self, request):
            self.requests.append(request)
            return ProviderResponse(
                {
                    "schema": "daytrace.workstream-digest.v2",
                    "workstreams": [
                        {
                            "label": "Overlap",
                            "confidence": "high",
                            "episode_ids": [episode_ids[0]],
                            "topics": [],
                            "outcomes": [],
                        }
                    ],
                    "unassigned_episode_ids": list(episode_ids),
                },
                "test",
                "fixed",
            )

        def merge(self, request):
            raise AssertionError("merge must not be called")

    provider = Provider()

    with pytest.raises(
        SummaryValidationError, match="invalid-episode-allocation"
    ):
        summarize_bundle(bundle, provider, plan)

    assert len(provider.requests) == 2
    assert "repair_instruction" not in provider.requests[0].payload
    assert "repair_instruction" in provider.requests[1].payload


def test_rejects_individually_oversized_episode(make_many_episode_bundle) -> None:
    with pytest.raises(EpisodeRequestTooLarge):
        build_summary_plan(
            make_many_episode_bundle(1, label_size=500),
            target_characters=200,
            max_characters=200,
        )


def test_rejects_oversized_merge_request() -> None:
    digest = WorkstreamDigest(
        (
            WorkstreamSummary(
                "x" * 500,
                Confidence.LOW,
                ("episode-001",),
                (),
                (OutcomeSummary("state", OutcomeStrength.OBSERVED, ("episode-001",)),),
            ),
        ),
        (),
    )
    with pytest.raises(MergeRequestTooLarge):
        build_merge_request((digest,), max_characters=100)


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


def test_mixed_episode_evidence_may_support_another_workstream() -> None:
    payload = {
        "schema": "daytrace.workstream-digest.v2",
        "workstreams": [
            {
                "label": "Primary owner",
                "confidence": "high",
                "episode_ids": ["episode-001"],
                "topics": [],
                "outcomes": [],
            },
            {
                "label": "Interleaved work",
                "confidence": "medium",
                "episode_ids": ["episode-002"],
                "topics": [
                    {
                        "text": "Work also visible in a mixed episode",
                        "evidence": ["episode-001", "episode-002"],
                    }
                ],
                "outcomes": [],
            },
        ],
        "unassigned_episode_ids": [],
    }

    digest = validate_digest(payload, {"episode-001", "episode-002"})

    assert digest.workstreams[1].topics[0].evidence == (
        "episode-001",
        "episode-002",
    )


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


@pytest.mark.parametrize(
    ("payload", "allowed", "code", "field"),
    [
        (
            {
                "schema": "daytrace.workstream-digest.v2",
                "workstreams": [
                    {
                        "label": "Work",
                        "confidence": "high",
                        "episode_ids": [],
                        "topics": [],
                        "outcomes": [],
                    }
                ],
                "unassigned_episode_ids": ["episode-001"],
            },
            {"episode-001"},
            "empty-ids",
            "workstreams[0].episode_ids",
        ),
        (
            {
                "schema": "daytrace.workstream-digest.v2",
                "workstreams": [
                    {
                        "label": "Work",
                        "confidence": "high",
                        "episode_ids": ["episode-001", "episode-001"],
                        "topics": [],
                        "outcomes": [],
                    }
                ],
                "unassigned_episode_ids": [],
            },
            {"episode-001"},
            "duplicate-ids",
            "workstreams[0].episode_ids",
        ),
        (
            {
                "schema": "daytrace.workstream-digest.v2",
                "workstreams": [
                    {
                        "label": "Work",
                        "confidence": "high",
                        "episode_ids": ["episode-999"],
                        "topics": [],
                        "outcomes": [],
                    }
                ],
                "unassigned_episode_ids": [],
            },
            {"episode-001"},
            "unknown-ids",
            "workstreams[0].episode_ids",
        ),
        (
            {
                "schema": "daytrace.workstream-digest.v2",
                "workstreams": [
                    {
                        "label": "Work",
                        "confidence": "high",
                        "episode_ids": ["episode-001"],
                        "topics": [{"text": "Topic", "evidence": []}],
                        "outcomes": [],
                    }
                ],
                "unassigned_episode_ids": [],
            },
            {"episode-001"},
            "empty-evidence",
            "workstreams[0].topics[0].evidence",
        ),
    ],
)
def test_validation_failures_have_stable_codes_and_paths(
    payload, allowed, code, field
) -> None:
    with pytest.raises(SummaryValidationError) as caught:
        validate_digest(payload, allowed)

    assert caught.value.code == code
    assert caught.value.field == field


def test_invalid_allocation_has_stable_code_and_path() -> None:
    payload = valid_payload()
    payload["unassigned_episode_ids"] = ["episode-001"]

    with pytest.raises(SummaryValidationError) as caught:
        validate_digest(payload, {"episode-001"})

    assert caught.value.code == "invalid-episode-allocation"
    assert caught.value.field == "episode-allocation"


def test_chunk_validation_failure_has_safe_request_context(
    make_episode_bundle,
) -> None:
    bundle = make_episode_bundle()
    plan = build_summary_plan(bundle)

    class Provider:
        def summarize(self, request):
            return ProviderResponse(
                {
                    "schema": "daytrace.workstream-digest.v2",
                    "workstreams": [
                        {
                            "label": "Private generated label",
                            "confidence": "high",
                            "episode_ids": [],
                            "topics": [],
                            "outcomes": [],
                        }
                    ],
                    "unassigned_episode_ids": list(request.episode_ids),
                },
                "openai",
                "fixed",
                response_id="resp_test",
                request_id="req_test",
            )

        def merge(self, request):
            raise AssertionError("merge must not be called")

    with pytest.raises(SummaryValidationError) as caught:
        summarize_bundle(bundle, Provider(), plan)

    context = caught.value.context
    assert context.stage.value == "chunk"
    assert context.call_index == 1
    assert context.request_character_count == plan.requests[0].character_count
    assert context.item_ids == plan.requests[0].episode_ids
    assert context.response_id == "resp_test"
    assert context.request_id == "req_test"
    assert "Private generated label" not in str(caught.value)


def test_merge_validation_failure_has_safe_request_context(
    make_many_episode_bundle,
) -> None:
    bundle = make_many_episode_bundle(3, label_size=120)
    plan = build_summary_plan(bundle, target_characters=650, max_characters=900)

    class Provider:
        def summarize(self, request):
            return ProviderResponse(
                {
                    "schema": "daytrace.workstream-digest.v2",
                    "workstreams": [
                        {
                            "label": "Chunk",
                            "confidence": "medium",
                            "episode_ids": list(request.episode_ids),
                            "topics": [],
                            "outcomes": [],
                        }
                    ],
                    "unassigned_episode_ids": [],
                },
                "openai",
                "fixed",
            )

        def merge(self, request):
            return ProviderResponse(
                {
                    "schema": "daytrace.workstream-merge.v1",
                    "groups": [
                        {
                            "label": "Duplicate allocation",
                            "confidence": "medium",
                            "provisional_ids": [
                                request.provisional_ids[0],
                                request.provisional_ids[0],
                            ],
                        }
                    ],
                },
                "openai",
                "fixed",
                response_id="resp_merge",
                request_id="req_merge",
            )

    with pytest.raises(SummaryValidationError) as caught:
        summarize_bundle(bundle, Provider(), plan)

    context = caught.value.context
    assert context.stage.value == "merge"
    assert context.call_index == len(plan.requests) + 1
    assert context.item_ids
    assert context.response_id == "resp_merge"
    assert context.request_id == "req_merge"


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

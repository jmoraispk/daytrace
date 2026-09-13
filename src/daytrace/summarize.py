from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from daytrace.cloud_privacy import minimize_cloud_text, minimize_cloud_title
from daytrace.episode import compact_sessions
from daytrace.models import (
    ActivityEpisode,
    Confidence,
    EpisodeBundle,
    MergeGroup,
    MergeRequest,
    OutcomeStrength,
    OutcomeSummary,
    ProviderResponse,
    SessionBundle,
    SummaryFailureContext,
    SummaryPass,
    SummaryPlan,
    SummaryProvenance,
    SummaryRequest,
    TopicSummary,
    WorkstreamDigest,
    WorkstreamSummary,
)
from daytrace.sanitize import sanitize_generated_text
from daytrace.summary_diagnostics import safe_response_shape


PROMPT_SCHEMA = "daytrace.workstream-prompt.v6"
REQUEST_SCHEMA = "daytrace.summary-request.v2"
DIGEST_SCHEMA = "daytrace.workstream-digest.v2"
MAX_REQUEST_CHARACTERS = 100_000
TARGET_REQUEST_CHARACTERS = 80_000
CATEGORY_ORDER = ("anchor", "application", "activity-label", "outcome-signal")
ALLOCATION_REPAIR_INSTRUCTION = (
    "Partition every supplied episode ID exactly once across "
    "workstreams[].episode_ids and unassigned_episode_ids."
)


class SummaryRequestTooLarge(RuntimeError):
    """The minimized request exceeds the fixed provider-input ceiling."""


class EpisodeRequestTooLarge(SummaryRequestTooLarge):
    """One compact episode cannot fit in a bounded provider request."""


class MergeRequestTooLarge(SummaryRequestTooLarge):
    """The constrained merge request exceeds the provider-input ceiling."""


class SummaryValidationError(RuntimeError):
    """A provider response does not match the workstream schema."""

    def __init__(
        self,
        code: str,
        field: str = "response",
        context: SummaryFailureContext | None = None,
        response_shape: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.field = field
        self.context = context
        self.response_shape = response_shape
        super().__init__(f"{code} at {field}")


@runtime_checkable
class SummaryProvider(Protocol):
    def summarize(self, request: SummaryRequest) -> ProviderResponse: ...

    def merge(self, request: MergeRequest) -> ProviderResponse: ...


def _clean_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        clean = {key: value for key, value in item.items() if value is not None}
        marker = json.dumps(clean, ensure_ascii=False, sort_keys=True)
        if clean and marker not in seen:
            seen.add(marker)
            result.append(clean)
    return result


def _episode_payload(
    episode: ActivityEpisode, categories: set[str]
) -> dict[str, object]:
    anchors = _clean_items(
        [
            {
                "kind": item.kind,
                "value": (
                    minimize_cloud_title(None, item.value)
                    if item.kind == "title"
                    else minimize_cloud_text(item.value)
                ),
            }
            for item in episode.anchors
        ]
    )
    applications = _clean_items(
        [
            {"value": minimize_cloud_text(item.value), "count": item.count}
            for item in episode.applications
        ]
    )
    activity_labels = _clean_items(
        [
            {"value": minimize_cloud_title(None, item.value), "count": item.count}
            for item in episode.activity_labels
        ]
    )
    outcome_signals = _clean_items(
        [
            {"code": item.code, "label": minimize_cloud_text(item.label)}
            for item in episode.outcome_signals
        ]
    )
    for values, category in (
        (anchors, "anchor"),
        (applications, "application"),
        (activity_labels, "activity-label"),
        (outcome_signals, "outcome-signal"),
    ):
        if values:
            categories.add(category)
    payload: dict[str, object] = {
        "id": episode.episode_id,
        "start": episode.start.isoformat(),
        "end": episode.end.isoformat(),
        "active_seconds": episode.active_seconds,
        "focused_seconds": episode.focused_seconds,
        "label": minimize_cloud_title(None, episode.label),
        "anchors": anchors,
        "applications": applications,
        "activity_labels": activity_labels,
        "transition_count": len(episode.session_ids),
        "outcome_signals": outcome_signals,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _request_for_episodes(
    bundle: EpisodeBundle, episodes: Sequence[ActivityEpisode]
) -> SummaryRequest:
    categories: set[str] = set()
    payload: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "prompt_schema": PROMPT_SCHEMA,
        "date": bundle.day.isoformat(),
        "timezone": bundle.timezone_name,
        "focused_seconds": bundle.focused_seconds,
        "episodes": [_episode_payload(item, categories) for item in episodes],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return SummaryRequest(
        schema=REQUEST_SCHEMA,
        pass_kind=SummaryPass.CHUNK,
        payload=payload,
        character_count=len(serialized),
        episode_ids=tuple(item.episode_id for item in episodes),
        data_categories=tuple(item for item in CATEGORY_ORDER if item in categories),
    )


def _episodes(bundle: EpisodeBundle | SessionBundle) -> EpisodeBundle:
    return bundle if isinstance(bundle, EpisodeBundle) else compact_sessions(bundle)


def build_summary_plan(
    bundle: EpisodeBundle | SessionBundle,
    *,
    target_characters: int = TARGET_REQUEST_CHARACTERS,
    max_characters: int = MAX_REQUEST_CHARACTERS,
) -> SummaryPlan:
    resolved = _episodes(bundle)
    groups: list[list[ActivityEpisode]] = []
    current: list[ActivityEpisode] = []
    for episode in resolved.episodes:
        candidate = (*current, episode)
        candidate_request = _request_for_episodes(resolved, candidate)
        if current and candidate_request.character_count > target_characters:
            groups.append(current)
            current = [episode]
        else:
            current.append(episode)
        if _request_for_episodes(resolved, current).character_count > max_characters:
            raise EpisodeRequestTooLarge()
    if current or not groups:
        groups.append(current)
    requests = tuple(_request_for_episodes(resolved, group) for group in groups)
    if any(request.character_count > max_characters for request in requests):
        raise EpisodeRequestTooLarge()
    categories = tuple(
        item
        for item in CATEGORY_ORDER
        if any(item in request.data_categories for request in requests)
    )
    return SummaryPlan(
        requests=requests,
        episode_count=len(resolved.episodes),
        input_character_count=sum(item.character_count for item in requests),
        planned_request_count=len(requests) + (1 if len(requests) > 1 else 0),
        data_categories=categories,
    )


def build_summary_request(bundle: EpisodeBundle | SessionBundle) -> SummaryRequest:
    """Compatibility wrapper for callers that expect one bounded request."""
    return build_summary_plan(bundle).requests[0]


def _bounded_text(value: object, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SummaryValidationError("invalid-text", field)
    return sanitize_generated_text(value.strip())


def _object(value: object, field: str, required: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != required:
        raise SummaryValidationError("invalid-shape", field)
    return value


def _list(value: object, field: str, limit: int) -> list[object]:
    if not isinstance(value, list) or len(value) > limit:
        raise SummaryValidationError("invalid-shape", field)
    return value


def _evidence(value: object, allowed: set[str], field: str) -> tuple[str, ...]:
    values = _list(value, field, 100)
    if not values:
        raise SummaryValidationError("empty-evidence", field)
    result = tuple(_bounded_text(item, field, 50) for item in values)
    if len(result) != len(set(result)):
        raise SummaryValidationError("duplicate-ids", field)
    if not set(result) <= allowed:
        raise SummaryValidationError("unknown-ids", field)
    return result


def _ids(value: object, allowed: set[str], field: str) -> tuple[str, ...]:
    values = _list(value, field, 100)
    result = tuple(_bounded_text(item, field, 50) for item in values)
    if not result:
        raise SummaryValidationError("empty-ids", field)
    if len(result) != len(set(result)):
        raise SummaryValidationError("duplicate-ids", field)
    if not set(result) <= allowed:
        raise SummaryValidationError("unknown-ids", field)
    return result


def validate_digest(
    payload: Mapping[str, object], allowed_episode_ids: set[str]
) -> WorkstreamDigest:
    root = _object(
        payload,
        "response",
        {"schema", "workstreams", "unassigned_episode_ids"},
    )
    if root["schema"] != DIGEST_SCHEMA:
        raise SummaryValidationError("invalid-schema", "schema")
    workstreams: list[WorkstreamSummary] = []
    allocated: list[str] = []
    for index, raw_workstream in enumerate(
        _list(root["workstreams"], "workstreams", 30)
    ):
        field = f"workstreams[{index}]"
        value = _object(
            raw_workstream,
            field,
            {"label", "confidence", "episode_ids", "topics", "outcomes"},
        )
        episode_ids = _ids(
            value["episode_ids"], allowed_episode_ids, f"{field}.episode_ids"
        )
        allocated.extend(episode_ids)
        try:
            confidence = Confidence(
                _bounded_text(value["confidence"], f"{field}.confidence", 20)
            )
        except ValueError:
            raise SummaryValidationError(
                "invalid-enum", f"{field}.confidence"
            ) from None
        topics: list[TopicSummary] = []
        for topic_index, raw_topic in enumerate(
            _list(value["topics"], f"{field}.topics", 20)
        ):
            topic_field = f"{field}.topics[{topic_index}]"
            topic = _object(raw_topic, topic_field, {"text", "evidence"})
            topics.append(
                TopicSummary(
                    _bounded_text(topic["text"], f"{topic_field}.text"),
                    _evidence(
                        topic["evidence"],
                        allowed_episode_ids,
                        f"{topic_field}.evidence",
                    ),
                )
            )
        outcomes: list[OutcomeSummary] = []
        for outcome_index, raw_outcome in enumerate(
            _list(value["outcomes"], f"{field}.outcomes", 20)
        ):
            outcome_field = f"{field}.outcomes[{outcome_index}]"
            outcome = _object(
                raw_outcome, outcome_field, {"text", "strength", "evidence"}
            )
            try:
                strength = OutcomeStrength(
                    _bounded_text(
                        outcome["strength"], f"{outcome_field}.strength", 20
                    )
                )
            except ValueError:
                raise SummaryValidationError(
                    "invalid-enum", f"{outcome_field}.strength"
                ) from None
            evidence = _evidence(
                outcome["evidence"],
                allowed_episode_ids,
                f"{outcome_field}.evidence",
            )
            if strength is not OutcomeStrength.NONE:
                outcomes.append(
                    OutcomeSummary(
                        _bounded_text(outcome["text"], f"{outcome_field}.text"),
                        strength,
                        evidence,
                    )
                )
        workstreams.append(
            WorkstreamSummary(
                label=_bounded_text(value["label"], f"{field}.label", 120),
                confidence=confidence,
                episode_ids=episode_ids,
                topics=tuple(topics),
                outcomes=tuple(outcomes),
            )
        )
    unassigned = tuple(
        _bounded_text(item, "unassigned_episode_ids", 50)
        for item in _list(
            root["unassigned_episode_ids"], "unassigned_episode_ids", 100
        )
    )
    allocation = allocated + list(unassigned)
    if len(allocation) != len(set(allocation)) or set(allocation) != allowed_episode_ids:
        raise SummaryValidationError(
            "invalid-episode-allocation", "episode-allocation"
        )
    return WorkstreamDigest(tuple(workstreams), unassigned)


def build_merge_request(
    digests: tuple[WorkstreamDigest, ...],
    *,
    max_characters: int = MAX_REQUEST_CHARACTERS,
) -> tuple[MergeRequest, Mapping[str, WorkstreamSummary]]:
    provisional: dict[str, WorkstreamSummary] = {}
    items: list[dict[str, object]] = []
    for chunk_index, digest in enumerate(digests, start=1):
        for stream_index, workstream in enumerate(digest.workstreams, start=1):
            provisional_id = f"provisional-{chunk_index:03d}-{stream_index:03d}"
            provisional[provisional_id] = workstream
            items.append(
                {
                    "id": provisional_id,
                    "label": workstream.label,
                    "confidence": workstream.confidence.value,
                    "episode_ids": list(workstream.episode_ids),
                    "topics": [
                        {"text": item.text, "evidence": list(item.evidence)}
                        for item in workstream.topics
                    ],
                    "outcomes": [
                        {
                            "text": item.text,
                            "strength": item.strength.value,
                            "evidence": list(item.evidence),
                        }
                        for item in workstream.outcomes
                    ],
                }
            )
    payload: dict[str, object] = {
        "schema": "daytrace.workstream-merge-request.v1",
        "provisional_workstreams": items,
    }
    character_count = len(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if character_count > max_characters:
        raise MergeRequestTooLarge()
    request = MergeRequest(
        schema="daytrace.workstream-merge-request.v1",
        pass_kind=SummaryPass.MERGE,
        payload=payload,
        character_count=character_count,
        provisional_ids=tuple(provisional),
    )
    return request, MappingProxyType(provisional)


def validate_merge(
    payload: Mapping[str, object], allowed: set[str]
) -> tuple[MergeGroup, ...]:
    root = _object(payload, "merge response", {"schema", "groups"})
    if root["schema"] != "daytrace.workstream-merge.v1":
        raise SummaryValidationError("invalid-schema", "schema")
    groups: list[MergeGroup] = []
    allocated: list[str] = []
    for index, raw_group in enumerate(_list(root["groups"], "groups", 30)):
        field = f"groups[{index}]"
        value = _object(
            raw_group, field, {"label", "confidence", "provisional_ids"}
        )
        provisional_ids = _ids(
            value["provisional_ids"], allowed, f"{field}.provisional_ids"
        )
        allocated.extend(provisional_ids)
        try:
            confidence = Confidence(
                _bounded_text(value["confidence"], f"{field}.confidence", 20)
            )
        except ValueError:
            raise SummaryValidationError(
                "invalid-enum", f"{field}.confidence"
            ) from None
        groups.append(
            MergeGroup(
                label=_bounded_text(value["label"], f"{field}.label", 120),
                confidence=confidence,
                provisional_ids=provisional_ids,
            )
        )
    if len(allocated) != len(set(allocated)):
        raise SummaryValidationError(
            "invalid-provisional-allocation", "provisional-allocation"
        )
    return tuple(groups)


def assemble_merged_digest(
    groups: tuple[MergeGroup, ...],
    provisional: Mapping[str, WorkstreamSummary],
    chunks: tuple[WorkstreamDigest, ...],
) -> WorkstreamDigest:
    merged_workstreams: list[WorkstreamSummary] = []
    for group in groups:
        selected = tuple(provisional[item] for item in group.provisional_ids)
        merged_workstreams.append(
            WorkstreamSummary(
                label=group.label,
                confidence=group.confidence,
                episode_ids=tuple(
                    episode_id
                    for item in selected
                    for episode_id in item.episode_ids
                ),
                topics=tuple(
                    dict.fromkeys(topic for item in selected for topic in item.topics)
                ),
                outcomes=tuple(
                    dict.fromkeys(
                        outcome for item in selected for outcome in item.outcomes
                    )
                ),
            )
        )
    group_index_by_id = {
        provisional_id: group_index
        for group_index, group in enumerate(groups)
        for provisional_id in group.provisional_ids
    }
    workstreams: list[WorkstreamSummary] = []
    emitted_groups: set[int] = set()
    for provisional_id, workstream in provisional.items():
        group_index = group_index_by_id.get(provisional_id)
        if group_index is None:
            workstreams.append(workstream)
        elif group_index not in emitted_groups:
            workstreams.append(merged_workstreams[group_index])
            emitted_groups.add(group_index)
    unassigned = tuple(
        dict.fromkeys(
            episode_id
            for chunk in chunks
            for episode_id in chunk.unassigned_episode_ids
        )
    )
    return WorkstreamDigest(tuple(workstreams), unassigned)


def validate_final_allocation(digest: WorkstreamDigest, allowed: set[str]) -> None:
    allocated = [
        episode_id
        for workstream in digest.workstreams
        for episode_id in workstream.episode_ids
    ] + list(digest.unassigned_episode_ids)
    if len(allocated) != len(set(allocated)) or set(allocated) != allowed:
        raise SummaryValidationError(
            "invalid-episode-allocation", "episode-allocation"
        )


def _sum_known(values: Iterable[int | None]) -> int | None:
    resolved = tuple(values)
    return (
        sum(value for value in resolved if value is not None)
        if any(value is not None for value in resolved)
        else None
    )


def _contextualized_validation_error(
    exc: SummaryValidationError,
    response: ProviderResponse,
    request: SummaryRequest | MergeRequest,
    call_index: int,
) -> SummaryValidationError:
    item_ids = (
        request.episode_ids
        if isinstance(request, SummaryRequest)
        else request.provisional_ids
    )
    return SummaryValidationError(
        exc.code,
        exc.field,
        SummaryFailureContext(
            provider=response.provider,
            model=response.model,
            stage=request.pass_kind,
            call_index=call_index,
            request_character_count=request.character_count,
            item_ids=item_ids,
            response_id=response.response_id,
            request_id=response.request_id,
        ),
        safe_response_shape(response.payload, set(item_ids)),
    )


def _allocation_repair_request(request: SummaryRequest) -> SummaryRequest | None:
    payload = dict(request.payload)
    payload["repair_instruction"] = ALLOCATION_REPAIR_INSTRUCTION
    character_count = len(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if character_count > MAX_REQUEST_CHARACTERS:
        return None
    return replace(request, payload=payload, character_count=character_count)


def summarize_bundle(
    bundle: EpisodeBundle | SessionBundle,
    provider: SummaryProvider,
    plan: SummaryPlan | None = None,
) -> tuple[WorkstreamDigest, SummaryProvenance]:
    resolved_bundle = _episodes(bundle)
    resolved_plan = plan or build_summary_plan(resolved_bundle)
    chunk_digests: list[WorkstreamDigest] = []
    responses: list[ProviderResponse] = []
    last_request: SummaryRequest | MergeRequest | None = None
    for request in resolved_plan.requests:
        response = provider.summarize(request)
        responses.append(response)
        last_request = request
        try:
            chunk_digests.append(
                validate_digest(response.payload, set(request.episode_ids))
            )
        except SummaryValidationError as exc:
            repair_request = (
                _allocation_repair_request(request)
                if exc.code == "invalid-episode-allocation"
                else None
            )
            if repair_request is None:
                raise _contextualized_validation_error(
                    exc, response, request, len(responses)
                ) from None
            repair_response = provider.summarize(repair_request)
            responses.append(repair_response)
            last_request = repair_request
            try:
                chunk_digests.append(
                    validate_digest(
                        repair_response.payload, set(repair_request.episode_ids)
                    )
                )
            except SummaryValidationError as repair_exc:
                raise _contextualized_validation_error(
                    repair_exc,
                    repair_response,
                    repair_request,
                    len(responses),
                ) from None
    if len(chunk_digests) == 1:
        digest = chunk_digests[0]
    else:
        merge_request, provisional = build_merge_request(tuple(chunk_digests))
        merge_response = provider.merge(merge_request)
        responses.append(merge_response)
        last_request = merge_request
        try:
            groups = validate_merge(
                merge_response.payload, set(merge_request.provisional_ids)
            )
        except SummaryValidationError as exc:
            raise _contextualized_validation_error(
                exc, merge_response, merge_request, len(responses)
            ) from None
        digest = assemble_merged_digest(groups, provisional, tuple(chunk_digests))
    try:
        validate_final_allocation(
            digest, {item.episode_id for item in resolved_bundle.episodes}
        )
    except SummaryValidationError as exc:
        if not responses or last_request is None:
            raise
        raise _contextualized_validation_error(
            exc, responses[-1], last_request, len(responses)
        ) from None
    provenance = SummaryProvenance(
        provider=responses[0].provider,
        model=responses[0].model,
        prompt_schema=PROMPT_SCHEMA,
        input_tokens=_sum_known(item.input_tokens for item in responses),
        output_tokens=_sum_known(item.output_tokens for item in responses),
        request_count=len(responses),
    )
    return digest, provenance

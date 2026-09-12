from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from daytrace.cloud_privacy import minimize_cloud_text, minimize_cloud_title
from daytrace.episode import compact_sessions
from daytrace.models import (
    ActivityEpisode,
    Confidence,
    EpisodeBundle,
    OutcomeStrength,
    OutcomeSummary,
    ProviderResponse,
    SessionBundle,
    SummaryPass,
    SummaryPlan,
    SummaryProvenance,
    SummaryRequest,
    TopicSummary,
    WorkstreamDigest,
    WorkstreamSummary,
)
from daytrace.sanitize import sanitize_generated_text


PROMPT_SCHEMA = "daytrace.workstream-prompt.v2"
REQUEST_SCHEMA = "daytrace.summary-request.v2"
DIGEST_SCHEMA = "daytrace.workstream-digest.v2"
MAX_REQUEST_CHARACTERS = 100_000
CATEGORY_ORDER = ("anchor", "application", "activity-label", "outcome-signal")


class SummaryRequestTooLarge(RuntimeError):
    """The minimized request exceeds the fixed provider-input ceiling."""


class EpisodeRequestTooLarge(SummaryRequestTooLarge):
    """One compact episode cannot fit in a bounded provider request."""


class SummaryValidationError(RuntimeError):
    """A provider response does not match the workstream schema."""


@runtime_checkable
class SummaryProvider(Protocol):
    def summarize(self, request: SummaryRequest) -> ProviderResponse: ...


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
            {"kind": item.kind, "value": minimize_cloud_text(item.value)}
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
        "label": minimize_cloud_text(episode.label),
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


def build_summary_plan(bundle: EpisodeBundle | SessionBundle) -> SummaryPlan:
    resolved = _episodes(bundle)
    request = _request_for_episodes(resolved, resolved.episodes)
    if request.character_count > MAX_REQUEST_CHARACTERS:
        raise SummaryRequestTooLarge()
    return SummaryPlan(
        requests=(request,),
        episode_count=len(resolved.episodes),
        input_character_count=request.character_count,
        planned_request_count=1,
        data_categories=request.data_categories,
    )


def build_summary_request(bundle: EpisodeBundle | SessionBundle) -> SummaryRequest:
    """Compatibility wrapper for callers that expect one bounded request."""
    return build_summary_plan(bundle).requests[0]


def _bounded_text(value: object, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SummaryValidationError(f"invalid {field}")
    return sanitize_generated_text(value.strip())


def _object(value: object, field: str, required: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != required:
        raise SummaryValidationError(f"invalid {field}")
    return value


def _list(value: object, field: str, limit: int) -> list[object]:
    if not isinstance(value, list) or len(value) > limit:
        raise SummaryValidationError(f"invalid {field}")
    return value


def _evidence(value: object, allowed: set[str], field: str) -> tuple[str, ...]:
    values = _list(value, field, 100)
    if not values:
        raise SummaryValidationError(f"invalid {field}")
    result = tuple(_bounded_text(item, field, 50) for item in values)
    if len(result) != len(set(result)) or not set(result) <= allowed:
        raise SummaryValidationError(f"invalid {field}")
    return result


def _ids(value: object, allowed: set[str], field: str) -> tuple[str, ...]:
    values = _list(value, field, 100)
    result = tuple(_bounded_text(item, field, 50) for item in values)
    if not result or len(result) != len(set(result)) or not set(result) <= allowed:
        raise SummaryValidationError(f"invalid {field}")
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
        raise SummaryValidationError("invalid schema")
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
            raise SummaryValidationError(f"invalid {field}.confidence") from None
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
                        topic["evidence"], set(episode_ids), f"{topic_field}.evidence"
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
                    f"invalid {outcome_field}.strength"
                ) from None
            evidence = _evidence(
                outcome["evidence"], set(episode_ids), f"{outcome_field}.evidence"
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
        raise SummaryValidationError("invalid episode allocation")
    return WorkstreamDigest(tuple(workstreams), unassigned)


def summarize_bundle(
    bundle: EpisodeBundle | SessionBundle,
    provider: SummaryProvider,
    plan: SummaryPlan | None = None,
) -> tuple[WorkstreamDigest, SummaryProvenance]:
    resolved_bundle = _episodes(bundle)
    resolved_plan = plan or build_summary_plan(resolved_bundle)
    if len(resolved_plan.requests) != 1:
        raise SummaryRequestTooLarge()
    response = provider.summarize(resolved_plan.requests[0])
    digest = validate_digest(
        response.payload, set(resolved_plan.requests[0].episode_ids)
    )
    provenance = SummaryProvenance(
        provider=response.provider,
        model=response.model,
        prompt_schema=PROMPT_SCHEMA,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        request_count=1,
    )
    return digest, provenance

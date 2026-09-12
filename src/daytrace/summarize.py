from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import PurePath, PureWindowsPath
from typing import Protocol, runtime_checkable

from daytrace.models import (
    Confidence,
    OutcomeStrength,
    OutcomeSummary,
    ProviderResponse,
    SessionBundle,
    SummaryProvenance,
    SummaryRequest,
    TopicSummary,
    WorkstreamDigest,
    WorkstreamSummary,
)


PROMPT_SCHEMA = "daytrace.workstream-prompt.v1"
REQUEST_SCHEMA = "daytrace.summary-request.v1"
DIGEST_SCHEMA = "daytrace.workstream-digest.v1"
MAX_REQUEST_CHARACTERS = 100_000


class SummaryRequestTooLarge(RuntimeError):
    """The sanitized request exceeds the fixed provider-input ceiling."""


class SummaryValidationError(RuntimeError):
    """A provider response does not match the workstream schema."""


@runtime_checkable
class SummaryProvider(Protocol):
    def summarize(self, request: SummaryRequest) -> ProviderResponse: ...


def _basename(value: str) -> str:
    path = PureWindowsPath(value) if "\\" in value or ":" in value else PurePath(value)
    return path.name


def _session_payload(session, categories: set[str]) -> dict[str, object]:
    applications = sorted({item.app for item in session.slices if item.app})
    titles = sorted(
        {
            value
            for item in session.slices
            for value in (
                item.title,
                *(context.title for context in item.contexts),
            )
            if value
        }
    )
    contexts: list[dict[str, object]] = []
    seen_contexts: set[tuple[tuple[str, object], ...]] = set()
    for item in session.slices:
        for context in item.contexts:
            safe: dict[str, object] = {}
            if context.project:
                safe["editor_project"] = _basename(context.project)
                categories.add("editor-project")
            if context.file:
                safe["file_name"] = _basename(context.file)
                categories.add("file-name")
            if context.url_path:
                safe["repository_path"] = context.url_path
                categories.add("repository-path")
            elif context.url_host:
                safe["domain"] = context.url_host
                categories.add("browser-domain")
            if context.language:
                safe["language"] = context.language
                categories.add("language")
            if context.title:
                safe["title"] = context.title
            marker = tuple(sorted(safe.items()))
            if safe and marker not in seen_contexts:
                seen_contexts.add(marker)
                contexts.append(safe)
    if applications:
        categories.add("application")
    if titles:
        categories.add("title")
    return {
        "id": session.session_id,
        "start": session.start.isoformat(),
        "end": session.end.isoformat(),
        "active_seconds": session.active_seconds,
        "focused_seconds": session.focused_seconds,
        "label": session.label,
        "applications": applications,
        "titles": titles,
        "contexts": contexts,
        "outcome_signals": [
            {
                "code": signal.code,
                "label": signal.label,
            }
            for signal in session.outcome_signals
        ],
    }


def build_summary_request(bundle: SessionBundle) -> SummaryRequest:
    categories: set[str] = set()
    sessions = [
        _session_payload(item, categories)
        for item in sorted(bundle.sessions, key=lambda value: value.session_id)
    ]
    payload: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "prompt_schema": PROMPT_SCHEMA,
        "date": bundle.day.isoformat(),
        "timezone": bundle.timezone_name,
        "focused_seconds": bundle.focused_seconds,
        "sessions": sessions,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(serialized) > MAX_REQUEST_CHARACTERS:
        raise SummaryRequestTooLarge()
    category_order = (
        "application",
        "browser-domain",
        "editor-project",
        "file-name",
        "language",
        "repository-path",
        "title",
    )
    return SummaryRequest(
        schema=REQUEST_SCHEMA,
        payload=payload,
        character_count=len(serialized),
        session_count=len(sessions),
        data_categories=tuple(item for item in category_order if item in categories),
    )


def _bounded_text(value: object, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SummaryValidationError(f"invalid {field}")
    return value.strip()


def _object(
    value: object, field: str, required: set[str]
) -> Mapping[str, object]:
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


def _session_ids(value: object, allowed: set[str], field: str) -> tuple[str, ...]:
    values = _list(value, field, 100)
    result = tuple(_bounded_text(item, field, 50) for item in values)
    if not result or len(result) != len(set(result)) or not set(result) <= allowed:
        raise SummaryValidationError(f"invalid {field}")
    return result


def validate_digest(
    payload: Mapping[str, object], bundle: SessionBundle
) -> WorkstreamDigest:
    root = _object(
        payload,
        "response",
        {"schema", "workstreams", "unassigned_session_ids"},
    )
    if root["schema"] != DIGEST_SCHEMA:
        raise SummaryValidationError("invalid schema")
    allowed = {item.session_id for item in bundle.sessions}
    workstream_values = _list(root["workstreams"], "workstreams", 30)
    workstreams: list[WorkstreamSummary] = []
    allocated: list[str] = []
    for index, raw_workstream in enumerate(workstream_values):
        field = f"workstreams[{index}]"
        value = _object(
            raw_workstream,
            field,
            {"label", "confidence", "session_ids", "topics", "outcomes"},
        )
        session_ids = _session_ids(value["session_ids"], allowed, f"{field}.session_ids")
        allocated.extend(session_ids)
        try:
            confidence = Confidence(_bounded_text(value["confidence"], f"{field}.confidence", 20))
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
                        topic["evidence"], set(session_ids), f"{topic_field}.evidence"
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
                    _bounded_text(outcome["strength"], f"{outcome_field}.strength", 20)
                )
            except ValueError:
                raise SummaryValidationError(
                    f"invalid {outcome_field}.strength"
                ) from None
            evidence = _evidence(
                outcome["evidence"], set(session_ids), f"{outcome_field}.evidence"
            )
            text = _bounded_text(outcome["text"], f"{outcome_field}.text")
            if strength is not OutcomeStrength.NONE:
                outcomes.append(
                    OutcomeSummary(
                        text,
                        strength,
                        evidence,
                    )
                )
        workstreams.append(
            WorkstreamSummary(
                label=_bounded_text(value["label"], f"{field}.label", 120),
                confidence=confidence,
                session_ids=session_ids,
                topics=tuple(topics),
                outcomes=tuple(outcomes),
            )
        )

    unassigned_values = _list(
        root["unassigned_session_ids"], "unassigned_session_ids", 100
    )
    unassigned = tuple(
        _bounded_text(item, "unassigned_session_ids", 50)
        for item in unassigned_values
    )
    allocation = allocated + list(unassigned)
    if len(allocation) != len(set(allocation)) or set(allocation) != allowed:
        raise SummaryValidationError("invalid session allocation")
    return WorkstreamDigest(tuple(workstreams), unassigned)


def summarize_bundle(
    bundle: SessionBundle, provider: SummaryProvider
) -> tuple[WorkstreamDigest, SummaryProvenance]:
    request = build_summary_request(bundle)
    response = provider.summarize(request)
    digest = validate_digest(response.payload, bundle)
    provenance = SummaryProvenance(
        provider=response.provider,
        model=response.model,
        prompt_schema=PROMPT_SCHEMA,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
    return digest, provenance

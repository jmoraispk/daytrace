from __future__ import annotations

import json
import re
from collections.abc import Mapping

from daytrace import __version__
from daytrace.models import SummaryFailureContext


SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
SAFE_CODE = re.compile(r"^[a-z0-9-]{1,80}$")
SAFE_FIELD = re.compile(r"^[A-Za-z0-9_.\[\]-]{1,240}$")
SHAPE_LIST_FIELDS = {
    "known_allocated_ids",
    "known_unassigned_ids",
    "known_evidence_ids",
    "known_provisional_ids",
}
SHAPE_COUNT_FIELDS = {
    "workstream_count",
    "topic_count",
    "outcome_count",
    "group_count",
    "unknown_id_count",
    "duplicate_id_count",
}


def safe_identifier(value: object, fallback: str) -> str:
    if isinstance(value, str) and SAFE_IDENTIFIER.fullmatch(value):
        return value
    return fallback


def safe_failure_code(value: object) -> str:
    if isinstance(value, str) and SAFE_CODE.fullmatch(value):
        return value
    return "redacted-code"


def safe_failure_field(value: object) -> str:
    if isinstance(value, str) and SAFE_FIELD.fullmatch(value):
        return value
    return "redacted-field"


def _items(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def safe_response_shape(
    payload: object, allowed_ids: set[str]
) -> Mapping[str, object]:
    root = payload if isinstance(payload, Mapping) else {}
    allocated: list[str] = []
    unassigned: list[str] = []
    evidence: list[str] = []
    provisional: list[str] = []
    unknown_count = 0
    workstreams = _items(root.get("workstreams"))
    groups = _items(root.get("groups"))
    topic_count = 0
    outcome_count = 0

    def collect(value: object, destination: list[str]) -> None:
        nonlocal unknown_count
        for item in _items(value):
            if isinstance(item, str) and item in allowed_ids:
                destination.append(item)
            else:
                unknown_count += 1

    for raw_workstream in workstreams:
        if not isinstance(raw_workstream, Mapping):
            continue
        collect(raw_workstream.get("episode_ids"), allocated)
        topics = _items(raw_workstream.get("topics"))
        outcomes = _items(raw_workstream.get("outcomes"))
        topic_count += len(topics)
        outcome_count += len(outcomes)
        for raw_topic in topics:
            if isinstance(raw_topic, Mapping):
                collect(raw_topic.get("evidence"), evidence)
        for raw_outcome in outcomes:
            if isinstance(raw_outcome, Mapping):
                collect(raw_outcome.get("evidence"), evidence)
    collect(root.get("unassigned_episode_ids"), unassigned)
    for raw_group in groups:
        if isinstance(raw_group, Mapping):
            collect(raw_group.get("provisional_ids"), provisional)

    collections = (allocated + unassigned, evidence, provisional)
    duplicate_count = sum(len(items) - len(set(items)) for items in collections)
    return {
        "workstream_count": len(workstreams),
        "topic_count": topic_count,
        "outcome_count": outcome_count,
        "group_count": len(groups),
        "known_allocated_ids": sorted(set(allocated)),
        "known_unassigned_ids": sorted(set(unassigned)),
        "known_evidence_ids": sorted(set(evidence)),
        "known_provisional_ids": sorted(set(provisional)),
        "unknown_id_count": unknown_count,
        "duplicate_id_count": duplicate_count,
    }


def _safe_shape(value: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    for key in SHAPE_COUNT_FIELDS:
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            result[key] = item
    for key in SHAPE_LIST_FIELDS:
        item = value.get(key)
        if isinstance(item, list):
            result[key] = [
                candidate
                for candidate in item
                if isinstance(candidate, str) and SAFE_IDENTIFIER.fullmatch(candidate)
            ]
    return result


def render_summary_failure_json(
    *,
    provider: object,
    model: object,
    code: object,
    field: object | None = None,
    context: SummaryFailureContext | None = None,
    response_shape: Mapping[str, object] | None = None,
    request_id: object | None = None,
) -> str:
    validation: dict[str, object] = {"code": safe_failure_code(code)}
    payload: dict[str, object] = {
        "schema": "daytrace.ai-failure.v1",
        "daytrace_version": __version__,
        "provider": safe_identifier(provider, "[redacted-provider]"),
        "model": safe_identifier(model, "[redacted-model]"),
        "validation": validation,
        "response_shape": _safe_shape(response_shape),
    }
    if isinstance(field, str) and SAFE_FIELD.fullmatch(field):
        validation["field"] = field
    if request_id is not None:
        payload["request_id"] = safe_identifier(request_id, "[redacted-request]")
    if context is not None:
        payload.update(
            {
                "stage": context.stage.value,
                "call_index": context.call_index,
                "request_character_count": context.request_character_count,
                "item_count": len(context.item_ids),
                "item_ids": [
                    safe_identifier(item, "[redacted-item]")
                    for item in context.item_ids
                ],
            }
        )
        if context.response_id is not None:
            payload["response_id"] = safe_identifier(
                context.response_id, "[redacted-response]"
            )
        if context.request_id is not None:
            payload["request_id"] = safe_identifier(
                context.request_id, "[redacted-request]"
            )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

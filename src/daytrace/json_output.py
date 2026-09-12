from __future__ import annotations

import json

from daytrace.models import (
    ActivityEpisode,
    ActivitySession,
    ActivitySlice,
    ContextSignal,
    EpisodeBundle,
    SessionBundle,
    SummaryProvenance,
    WorkstreamDigest,
)


def _context_dict(item: ContextSignal) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "kind": item.kind.value,
            "evidence_id": item.evidence_id,
            "title": item.title,
            "project": item.project,
            "file": item.file,
            "host": item.url_host,
            "path": item.url_path,
            "language": item.language,
        }.items()
        if value is not None
    }


def _slice_dict(item: ActivitySlice) -> dict[str, object]:
    return {
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "focused": item.focused,
        "duration_seconds": item.duration_seconds,
        "application": item.app,
        "title": item.title,
        "contexts": [_context_dict(context) for context in item.contexts],
        "evidence_ids": list(item.evidence_ids),
    }


def _session_dict(item: ActivitySession, *, details: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": item.session_id,
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "active_seconds": item.active_seconds,
        "focused_seconds": item.focused_seconds,
        "label": item.label,
        "outcome_signals": [
            {
                "code": signal.code,
                "label": signal.label,
                "evidence_ids": list(signal.evidence_ids),
            }
            for signal in item.outcome_signals
        ],
    }
    if details:
        payload["evidence_ids"] = list(item.evidence_ids)
        payload["slices"] = [_slice_dict(value) for value in item.slices]
    return payload


def render_session_json(bundle: SessionBundle, *, details: bool = False) -> str:
    payload = {
        "schema": "daytrace.session-bundle.v1",
        "date": bundle.day.isoformat(),
        "timezone": bundle.timezone_name,
        "timezone_status": "inferred_at_query",
        "focused_seconds": bundle.focused_seconds,
        "sessions": [
            _session_dict(item, details=details)
            for item in sorted(
                bundle.sessions, key=lambda value: (value.start, value.session_id)
            )
        ],
        "diagnostics": [
            {"code": item.code.value, "count": item.count}
            for item in bundle.diagnostics
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _episode_dict(item: ActivityEpisode, *, details: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": item.episode_id,
        "start": item.start.isoformat(),
        "end": item.end.isoformat(),
        "active_seconds": item.active_seconds,
        "focused_seconds": item.focused_seconds,
        "label": item.label,
        "anchors": [
            {"kind": value.kind, "value": value.value} for value in item.anchors
        ],
        "applications": [
            {"value": value.value, "count": value.count}
            for value in item.applications
        ],
        "activity_labels": [
            {"value": value.value, "count": value.count}
            for value in item.activity_labels
        ],
        "transition_count": len(item.session_ids),
        "outcome_signals": [
            {"code": value.code, "label": value.label}
            for value in item.outcome_signals
        ],
    }
    if details:
        payload["session_ids"] = list(item.session_ids)
        payload["evidence_ids"] = list(item.evidence_ids)
    return payload


def render_episode_json(
    bundle: EpisodeBundle, *, details: bool = False, raw: bool = False
) -> str:
    payload = {
        "schema": "daytrace.episode-bundle.v1",
        "date": bundle.day.isoformat(),
        "timezone": bundle.timezone_name,
        "timezone_status": "inferred_at_query",
        "focused_seconds": bundle.focused_seconds,
        "episodes": [
            _episode_dict(item, details=details)
            for item in sorted(
                bundle.episodes, key=lambda value: (value.start, value.episode_id)
            )
        ],
        "diagnostics": [
            {"code": item.code.value, "count": item.count}
            for item in bundle.diagnostics
        ],
    }
    if raw:
        payload["sessions"] = [
            _session_dict(item, details=True)
            for item in sorted(
                bundle.sessions, key=lambda value: (value.start, value.session_id)
            )
        ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def render_digest_json(
    bundle: EpisodeBundle,
    digest: WorkstreamDigest,
    provenance: SummaryProvenance,
    *,
    details: bool = False,
) -> str:
    episode_by_id = {item.episode_id: item for item in bundle.episodes}
    workstreams = []
    for item in digest.workstreams:
        episodes = tuple(episode_by_id[value] for value in item.episode_ids)
        workstreams.append(
            {
                "label": item.label,
                "confidence": item.confidence.value,
                "active_seconds": sum(value.active_seconds for value in episodes),
                "episode_ids": list(item.episode_ids),
                "topics": [
                    {"text": topic.text, "evidence": list(topic.evidence)}
                    for topic in item.topics
                ],
                "outcomes": [
                    {
                        "text": outcome.text,
                        "strength": outcome.strength.value,
                        "evidence": list(outcome.evidence),
                    }
                    for outcome in item.outcomes
                ],
                "activity": [
                    _episode_dict(value, details=details) for value in episodes
                ],
            }
        )
    payload = {
        "schema": "daytrace.workstream-report.v2",
        "date": bundle.day.isoformat(),
        "timezone": bundle.timezone_name,
        "timezone_status": "inferred_at_query",
        "focused_seconds": bundle.focused_seconds,
        "summary": {
            "provider": provenance.provider,
            "model": provenance.model,
            "prompt_schema": provenance.prompt_schema,
            "input_tokens": provenance.input_tokens,
            "output_tokens": provenance.output_tokens,
            "request_count": provenance.request_count,
        },
        "workstreams": workstreams,
        "unassigned_activity": [
            _episode_dict(episode_by_id[value], details=details)
            for value in digest.unassigned_episode_ids
        ],
        "diagnostics": [
            {"code": item.code.value, "count": item.count}
            for item in bundle.diagnostics
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

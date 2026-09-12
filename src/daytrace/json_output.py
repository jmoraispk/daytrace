from __future__ import annotations

import json

from daytrace.models import ActivitySession, ActivitySlice, ContextSignal, SessionBundle


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

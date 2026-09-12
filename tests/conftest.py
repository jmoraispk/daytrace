from datetime import datetime, timedelta, timezone

import pytest

from daytrace.models import (
    ActivityRecord,
    ActivitySession,
    ActivitySlice,
    ContextSignal,
    SanitizedObservation,
    SourceKind,
)


@pytest.fixture
def make_record():
    def factory(
        start_minute: int,
        duration_minutes: int,
        *,
        kind: SourceKind = SourceKind.WINDOW,
        bucket: str = "window",
        event_id: str = "1",
        app: str | None = "Code",
        title: str | None = "daytrace",
        project: str | None = None,
        file: str | None = None,
        url_host: str | None = None,
        url_path: str | None = None,
        language: str | None = None,
        status: str | None = None,
    ) -> ActivityRecord:
        start = datetime(2026, 9, 10, 9, tzinfo=timezone.utc) + timedelta(
            minutes=start_minute
        )
        return ActivityRecord(
            event_id=event_id,
            bucket_id=bucket,
            kind=kind,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            app=app,
            title=title,
            project=project,
            file=file,
            url_host=url_host,
            url_path=url_path,
            language=language,
            status=status,
        )

    return factory


@pytest.fixture
def make_session(make_slice):
    def factory(
        *,
        session_id: str = "session-001",
        label: str = "daytrace",
        slices: tuple[ActivitySlice, ...] | None = None,
    ) -> ActivitySession:
        resolved_slices = slices or (make_slice(0, 10),)
        focused = [item.duration_seconds for item in resolved_slices if item.focused]
        evidence_ids = tuple(
            sorted(
                {
                    evidence_id
                    for item in resolved_slices
                    for evidence_id in item.evidence_ids
                }
            )
        )
        return ActivitySession(
            session_id=session_id,
            start=min(item.start for item in resolved_slices),
            end=max(item.end for item in resolved_slices),
            active_seconds=sum(item.duration_seconds for item in resolved_slices),
            focused_seconds=sum(focused) if focused else None,
            label=label,
            slices=resolved_slices,
            evidence_ids=evidence_ids,
            outcome_signals=(),
        )

    return factory


@pytest.fixture
def make_sanitized():
    def factory(
        start_minute: int,
        duration_minutes: int,
        *,
        evidence_id: str = "evidence-0001",
        kind: SourceKind = SourceKind.WINDOW,
        app: str | None = "Code",
        title: str | None = "daytrace",
        project: str | None = None,
        file: str | None = None,
        url_host: str | None = None,
        url_path: str | None = None,
        language: str | None = None,
    ) -> SanitizedObservation:
        start = datetime(2026, 9, 10, 9, tzinfo=timezone.utc) + timedelta(
            minutes=start_minute
        )
        return SanitizedObservation(
            evidence_id=evidence_id,
            kind=kind,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            app=app,
            title=title,
            project=project,
            file=file,
            url_host=url_host,
            url_path=url_path,
            language=language,
        )

    return factory


@pytest.fixture
def make_slice():
    def factory(
        start_minute: int,
        duration_minutes: int,
        *,
        focused: bool = True,
        app: str | None = "Code",
        title: str | None = "daytrace",
        contexts: tuple[ContextSignal, ...] = (),
        evidence_ids: tuple[str, ...] = ("evidence-0001",),
        project: str | None = None,
        file: str | None = None,
        url_host: str | None = None,
        url_path: str | None = None,
        language: str | None = None,
    ) -> ActivitySlice:
        start = datetime(2026, 9, 10, 9, tzinfo=timezone.utc) + timedelta(
            minutes=start_minute
        )
        resolved_contexts = contexts
        if not resolved_contexts and any(
            value is not None
            for value in (project, file, url_host, url_path, language)
        ):
            resolved_contexts = (
                ContextSignal(
                    kind=SourceKind.BROWSER,
                    evidence_id=evidence_ids[0],
                    project=project,
                    file=file,
                    url_host=url_host,
                    url_path=url_path,
                    language=language,
                ),
            )
        return ActivitySlice(
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            focused=focused,
            app=app,
            title=title,
            contexts=resolved_contexts,
            evidence_ids=evidence_ids,
        )

    return factory

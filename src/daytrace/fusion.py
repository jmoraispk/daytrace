from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from daytrace.models import (
    ActivitySlice,
    ContextSignal,
    DiagnosticCode,
    SanitizedObservation,
    SourceKind,
)


BROWSER_APPS = ("edge", "chrome", "firefox", "brave", "opera", "safari")
EDITOR_APPS = ("code", "codium", "pycharm", "idea", "sublime", "zed")


def _app_matches(app: str | None, families: tuple[str, ...]) -> bool:
    folded = (app or "").casefold()
    return any(name in folded for name in families)


def _context(item: SanitizedObservation) -> ContextSignal:
    return ContextSignal(
        kind=item.kind,
        evidence_id=item.evidence_id,
        title=item.title,
        project=item.project,
        file=item.file,
        url_host=item.url_host,
        url_path=item.url_path,
        language=item.language,
    )


def _focused_slice(
    start,
    end,
    winner: SanitizedObservation,
    contexts: tuple[ContextSignal, ...],
) -> ActivitySlice:
    evidence = tuple(
        sorted({winner.evidence_id, *(item.evidence_id for item in contexts)})
    )
    return ActivitySlice(
        start,
        end,
        True,
        winner.app,
        winner.title,
        contexts,
        evidence,
    )


def _evidence_only_slice(
    start,
    end,
    covering: Iterable[SanitizedObservation],
) -> ActivitySlice:
    contexts = tuple(
        sorted((_context(item) for item in covering), key=lambda item: item.evidence_id)
    )
    evidence = tuple(item.evidence_id for item in contexts)
    return ActivitySlice(start, end, False, None, None, contexts, evidence)


def _merge_identical_touching(
    slices: tuple[ActivitySlice, ...],
) -> tuple[ActivitySlice, ...]:
    merged: list[ActivitySlice] = []
    for item in slices:
        previous = merged[-1] if merged else None
        if previous and previous.end == item.start and (
            previous.focused,
            previous.app,
            previous.title,
            previous.contexts,
        ) == (item.focused, item.app, item.title, item.contexts):
            merged[-1] = replace(
                previous,
                end=item.end,
                evidence_ids=tuple(
                    sorted({*previous.evidence_ids, *item.evidence_ids})
                ),
            )
        else:
            merged.append(item)
    return tuple(merged)


def fuse_observations(
    observations: Iterable[SanitizedObservation],
    diagnose: Callable[[DiagnosticCode], None],
) -> tuple[ActivitySlice, ...]:
    items = tuple(
        sorted(observations, key=lambda item: (item.start, item.evidence_id))
    )
    windows = tuple(item for item in items if item.kind is SourceKind.WINDOW)
    context_items = tuple(item for item in items if item.kind is not SourceKind.WINDOW)
    boundaries = sorted({point for item in items for point in (item.start, item.end)})
    output: list[ActivitySlice] = []

    for start, end in zip(boundaries, boundaries[1:]):
        covering_windows = [
            item for item in windows if item.start < end and item.end > start
        ]
        if covering_windows:
            if len(covering_windows) > 1:
                diagnose(DiagnosticCode.WINDOW_CONFLICT)
            winner = min(covering_windows, key=lambda item: item.evidence_id)
            contexts: list[ContextSignal] = []
            for item in context_items:
                if item.start >= end or item.end <= start:
                    continue
                attach = (
                    item.kind is SourceKind.BROWSER
                    and _app_matches(winner.app, BROWSER_APPS)
                ) or (
                    item.kind is SourceKind.EDITOR
                    and _app_matches(winner.app, EDITOR_APPS)
                )
                if attach:
                    contexts.append(_context(item))
            output.append(
                _focused_slice(
                    start,
                    end,
                    winner,
                    tuple(sorted(contexts, key=lambda item: item.evidence_id)),
                )
            )
        else:
            covering = [
                item for item in context_items if item.start < end and item.end > start
            ]
            if covering:
                output.append(_evidence_only_slice(start, end, covering))

    return _merge_identical_touching(tuple(output))

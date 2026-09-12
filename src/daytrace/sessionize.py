from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import PurePath, PureWindowsPath

from daytrace.models import (
    ActivitySession,
    ActivitySlice,
    DayWindow,
    DiagnosticCount,
    OutcomeSignal,
    SessionBundle,
)


MERGE_GAP = timedelta(seconds=60)
BRIDGE_LIMIT = timedelta(seconds=20)
SESSION_GAP = timedelta(minutes=5)
GENERIC = {
    "chatgpt",
    "powershell",
    "new tab",
    "inbox",
    "slack",
    "outlook",
    "new repository",
    "success page",
    "installation options",
}
STANDALONE_GENERIC = {
    "chatgpt",
    "powershell",
    "new tab",
    "inbox",
    "slack",
    "outlook",
}


def _specific_key(item: ActivitySlice) -> str | None:
    for context in item.contexts:
        if context.project:
            return context.project.casefold()
        if context.url_path:
            return context.url_path.casefold()
        if context.file:
            return context.file.casefold()
    if item.title and item.title.casefold() not in GENERIC:
        return item.title.casefold()
    return None


def _path_name(value: str) -> str:
    path = PureWindowsPath(value) if "\\" in value or ":" in value else PurePath(value)
    return path.name


def _label(item: ActivitySlice) -> str:
    for context in item.contexts:
        if context.project:
            return _path_name(context.project)
        if context.url_path:
            return context.url_path.strip("/")
        if context.title:
            return context.title
    return item.title or item.app or "Unknown activity"


def _generic_name(item: ActivitySlice) -> str:
    value = (item.title or item.app or "").casefold()
    return value.removesuffix(".exe")


def _evidence_for(slices: Iterable[ActivitySlice]) -> tuple[str, ...]:
    return tuple(sorted({item_id for item in slices for item_id in item.evidence_ids}))


def _outcome_signals(slices: tuple[ActivitySlice, ...]) -> tuple[OutcomeSignal, ...]:
    signals: list[OutcomeSignal] = []
    titles = [(item.title or "").casefold() for item in slices]
    for index, title in enumerate(titles[:-1]):
        matching_later = next(
            (
                later
                for later in slices[index + 1 :]
                if any(context.url_path for context in later.contexts)
            ),
            None,
        )
        if title == "new repository" and matching_later is not None:
            path = next(
                context.url_path
                for context in matching_later.contexts
                if context.url_path
            )
            signals.append(
                OutcomeSignal(
                    "named-repository-appeared",
                    f"Named repository appeared: {path.strip('/')}",
                    _evidence_for((slices[index], matching_later)),
                )
            )
            break
    if any(title in {"success page", "checkout success"} for title in titles):
        signals.append(
            OutcomeSignal(
                "checkout-success",
                "A checkout success state appeared",
                _evidence_for(slices),
            )
        )
    if any("installer" in (item.app or "").casefold() for item in slices):
        signals.append(
            OutcomeSignal(
                "installer-started",
                "An installer was started",
                _evidence_for(slices),
            )
        )
    return tuple(signals)


def _bridge_links(items: tuple[ActivitySlice, ...]) -> set[int]:
    links: set[int] = set()
    for index in range(1, len(items) - 1):
        previous_key = _specific_key(items[index - 1])
        next_key = _specific_key(items[index + 1])
        if (
            items[index].duration_seconds < BRIDGE_LIMIT.total_seconds()
            and previous_key is not None
            and previous_key == next_key
        ):
            links.update((index, index + 1))
    return links


def _starts_new_session(
    previous: ActivitySlice,
    current: ActivitySlice,
    boundary_index: int,
    bridge_links: set[int],
) -> bool:
    if boundary_index in bridge_links:
        return False
    if current.start - previous.end > SESSION_GAP:
        return True
    previous_key = _specific_key(previous)
    current_key = _specific_key(current)
    if previous_key and current_key:
        return previous_key != current_key
    if _generic_name(previous) in STANDALONE_GENERIC:
        return True
    if _generic_name(current) in STANDALONE_GENERIC:
        return True
    if previous_key is None and current_key is None:
        return _generic_name(previous) != _generic_name(current)
    return False


def _make_session(index: int, slices: tuple[ActivitySlice, ...]) -> ActivitySession:
    active_seconds = sum(item.duration_seconds for item in slices)
    focused = [item.duration_seconds for item in slices if item.focused]
    label_source = next((item for item in slices if _specific_key(item)), slices[0])
    return ActivitySession(
        session_id=f"session-{index:03d}",
        start=min(item.start for item in slices),
        end=max(item.end for item in slices),
        active_seconds=active_seconds,
        focused_seconds=sum(focused) if focused else None,
        label=_label(label_source),
        slices=slices,
        evidence_ids=_evidence_for(slices),
        outcome_signals=_outcome_signals(slices),
    )


def sessionize(
    day: date,
    window: DayWindow,
    slices: Iterable[ActivitySlice],
    diagnostics: tuple[DiagnosticCount, ...],
) -> SessionBundle:
    ordered = tuple(sorted(slices, key=lambda item: (item.start, item.end)))
    groups: list[list[ActivitySlice]] = []
    bridge_links = _bridge_links(ordered)
    for index, item in enumerate(ordered):
        if not groups or _starts_new_session(
            ordered[index - 1], item, index, bridge_links
        ):
            groups.append([item])
        else:
            groups[-1].append(item)

    sessions = tuple(
        _make_session(index, tuple(group))
        for index, group in enumerate(groups, start=1)
    )
    focused = [item.duration_seconds for item in ordered if item.focused]
    return SessionBundle(
        day=day,
        timezone_name=window.timezone_name,
        focused_seconds=sum(focused) if focused else None,
        sessions=sessions,
        diagnostics=diagnostics,
    )

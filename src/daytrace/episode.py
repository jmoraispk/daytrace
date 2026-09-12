from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from daytrace.models import (
    ActivityAnchor,
    ActivityEpisode,
    ActivityLabelCount,
    ActivitySession,
    EpisodeBundle,
    OutcomeSignal,
    SessionBundle,
)


BRIDGE_GAP = timedelta(minutes=5)
ONE_SIDED_GAP = timedelta(minutes=2)
GENERIC_LABELS = {
    "chatgpt",
    "powershell",
    "new tab",
    "inbox",
    "slack",
    "outlook",
    "explorer",
    "unknown",
    "unknown activity",
}
COMMUNICATION_TITLE = re.compile(
    r"(?i)(\(DM\).*Slack|\b(?:Inbox|Calendar).*Outlook|\bMicrosoft Teams$)"
)
ANCHOR_PRIORITY = {"repository": 0, "project": 1, "file": 2, "title": 3, "domain": 4}
OUTCOME_LABEL_CODES = {"named-repository-appeared", "checkout-success", "installer-started"}


class EpisodeInvariantError(RuntimeError):
    pass


def is_generic(value: str) -> bool:
    folded = value.casefold().removesuffix(".exe")
    return folded in GENERIC_LABELS or bool(COMMUNICATION_TITLE.search(value))


def session_anchors(session: ActivitySession) -> tuple[ActivityAnchor, ...]:
    found: dict[tuple[str, str], ActivityAnchor] = {}

    def add(kind: str, value: str | None) -> None:
        if not value:
            return
        normalized = " ".join(value.split())
        key = (kind, normalized.casefold())
        found.setdefault(key, ActivityAnchor(kind, normalized))

    for activity_slice in session.slices:
        for context in activity_slice.contexts:
            add("repository", context.url_path)
            add("project", context.project)
            add("file", context.file)
            if context.title and not is_generic(context.title):
                add("title", context.title)
            if context.url_host and not context.url_path:
                add("domain", context.url_host)
        if activity_slice.title and not is_generic(activity_slice.title):
            add("title", activity_slice.title)
    if not found and not is_generic(session.label):
        add("title", session.label)
    return tuple(
        sorted(
            found.values(),
            key=lambda item: (
                ANCHOR_PRIORITY[item.kind],
                item.value.casefold(),
                item.value,
            ),
        )
    )


def anchors_compatible(
    left: tuple[ActivityAnchor, ...], right: tuple[ActivityAnchor, ...]
) -> bool:
    return bool(
        {(item.kind, item.value.casefold()) for item in left}
        & {(item.kind, item.value.casefold()) for item in right}
    )


def _counts(values: list[str]) -> tuple[ActivityLabelCount, ...]:
    counted = Counter(values)
    return tuple(
        ActivityLabelCount(value, count)
        for value, count in sorted(
            counted.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
        )
    )


def _signals(sessions: tuple[ActivitySession, ...]) -> tuple[OutcomeSignal, ...]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for session in sessions:
        for signal in session.outcome_signals:
            evidence = grouped.setdefault((signal.code, signal.label), [])
            for evidence_id in signal.evidence_ids:
                if evidence_id not in evidence:
                    evidence.append(evidence_id)
    return tuple(
        OutcomeSignal(code, label, tuple(evidence))
        for (code, label), evidence in grouped.items()
    )


def _episode(index: int, sessions: tuple[ActivitySession, ...]) -> ActivityEpisode:
    anchors = tuple(
        dict.fromkeys(anchor for session in sessions for anchor in session_anchors(session))
    )
    anchors = tuple(
        sorted(
            anchors,
            key=lambda item: (
                ANCHOR_PRIORITY[item.kind],
                item.value.casefold(),
                item.value,
            ),
        )
    )
    signals = _signals(sessions)
    if anchors:
        label = anchors[0].value.removeprefix("/")
    else:
        named_outcome = next(
            (item.label for item in signals if item.code in OUTCOME_LABEL_CODES), None
        )
        label = named_outcome or sessions[0].label
    focused = tuple(
        session.focused_seconds
        for session in sessions
        if session.focused_seconds is not None
    )
    return ActivityEpisode(
        episode_id=f"episode-{index:03d}",
        start=min(item.start for item in sessions),
        end=max(item.end for item in sessions),
        active_seconds=sum(item.active_seconds for item in sessions),
        focused_seconds=sum(focused) if focused else None,
        label=label,
        session_ids=tuple(item.session_id for item in sessions),
        anchors=anchors,
        applications=_counts(
            [
                activity_slice.app
                for session in sessions
                for activity_slice in session.slices
                if activity_slice.app
            ]
        ),
        activity_labels=_counts([item.label for item in sessions]),
        outcome_signals=signals,
        evidence_ids=tuple(
            dict.fromkeys(
                evidence_id
                for session in sessions
                for evidence_id in session.evidence_ids
            )
        ),
    )


def compact_sessions(bundle: SessionBundle) -> EpisodeBundle:
    sessions = tuple(sorted(bundle.sessions, key=lambda item: (item.start, item.end)))
    anchors = tuple(session_anchors(item) for item in sessions)
    strong = [index for index, value in enumerate(anchors) if value]
    groups: list[set[int]] = []
    for session_index in strong:
        if groups:
            previous_index = max(groups[-1])
            if (
                anchors_compatible(anchors[previous_index], anchors[session_index])
                and sessions[session_index].start - sessions[previous_index].end
                <= BRIDGE_GAP
            ):
                groups[-1].update(range(previous_index + 1, session_index + 1))
                continue
        groups.append({session_index})

    assigned = {item for group in groups for item in group}
    for session_index, session in enumerate(sessions):
        if session_index in assigned:
            continue
        candidates: set[int] = set()
        for group_index, group in enumerate(groups):
            first = sessions[min(group)]
            last = sessions[max(group)]
            if last.end <= session.start and session.start - last.end <= ONE_SIDED_GAP:
                candidates.add(group_index)
            if session.end <= first.start and first.start - session.end <= ONE_SIDED_GAP:
                candidates.add(group_index)
        if len(candidates) == 1:
            group_index = candidates.pop()
            groups[group_index].add(session_index)
            assigned.add(session_index)

    unassigned = [index for index in range(len(sessions)) if index not in assigned]
    weak_groups: list[set[int]] = []
    for session_index in unassigned:
        if (
            weak_groups
            and session_index == max(weak_groups[-1]) + 1
            and sessions[session_index].start - sessions[max(weak_groups[-1])].end
            <= BRIDGE_GAP
        ):
            weak_groups[-1].add(session_index)
        else:
            weak_groups.append({session_index})
    groups.extend(weak_groups)
    groups.sort(key=lambda group: (sessions[min(group)].start, min(group)))

    episodes = tuple(
        _episode(
            episode_index,
            tuple(sessions[item] for item in sorted(group)),
        )
        for episode_index, group in enumerate(groups, start=1)
    )
    actual_members = [
        session_id for episode in episodes for session_id in episode.session_ids
    ]
    expected_members = [item.session_id for item in sessions]
    if len(actual_members) != len(set(actual_members)) or sorted(actual_members) != sorted(
        expected_members
    ):
        raise EpisodeInvariantError("episode membership was not conserved")
    if sum(item.active_seconds for item in episodes) != sum(
        item.active_seconds for item in sessions
    ):
        raise EpisodeInvariantError("episode duration was not conserved")
    return EpisodeBundle(
        day=bundle.day,
        timezone_name=bundle.timezone_name,
        focused_seconds=bundle.focused_seconds,
        episodes=episodes,
        sessions=sessions,
        diagnostics=bundle.diagnostics,
    )

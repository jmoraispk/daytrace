from dataclasses import FrozenInstanceError, replace
from math import isclose

import pytest

from daytrace.episode import compact_sessions
from daytrace.models import SessionBundle


def test_episode_factory_preserves_source_membership(make_episode) -> None:
    episode = make_episode(session_ids=("session-001", "session-002"))

    assert episode.episode_id == "episode-001"
    assert episode.session_ids == ("session-001", "session-002")
    with pytest.raises(FrozenInstanceError):
        episode.label = "changed"


def _repo_session(make_session, make_slice, session_id, start, repo, duration=1):
    activity_slice = make_slice(
        start,
        duration,
        title=repo,
        url_host="github.com",
        url_path=f"/example/{repo}",
        evidence_ids=(f"evidence-{session_id}",),
    )
    return make_session(session_id=session_id, label=repo, slices=(activity_slice,))


def _generic_session(make_session, make_slice, session_id, start, label="ChatGPT"):
    activity_slice = make_slice(
        start,
        1,
        app=label,
        title=label,
        evidence_ids=(f"evidence-{session_id}",),
    )
    return make_session(session_id=session_id, label=label, slices=(activity_slice,))


def _bundle(make_bundle, sessions):
    base = make_bundle()
    return SessionBundle(
        day=base.day,
        timezone_name=base.timezone_name,
        focused_seconds=sum(item.focused_seconds or 0 for item in sessions),
        sessions=tuple(sessions),
        diagnostics=base.diagnostics,
    )


def test_bridges_generic_activity_between_same_repository(
    make_bundle, make_session, make_slice
) -> None:
    sessions = (
        _repo_session(make_session, make_slice, "session-001", 0, "alpha"),
        _generic_session(make_session, make_slice, "session-002", 2),
        _repo_session(make_session, make_slice, "session-003", 5, "alpha"),
    )

    result = compact_sessions(_bundle(make_bundle, sessions))

    assert len(result.episodes) == 1
    assert result.episodes[0].session_ids == (
        "session-001",
        "session-002",
        "session-003",
    )


def test_does_not_bridge_incompatible_repositories(
    make_bundle, make_session, make_slice
) -> None:
    sessions = (
        _repo_session(make_session, make_slice, "session-001", 0, "alpha"),
        _generic_session(make_session, make_slice, "session-002", 2),
        _repo_session(make_session, make_slice, "session-003", 5, "beta"),
    )

    result = compact_sessions(_bundle(make_bundle, sessions))

    assert [episode.session_ids for episode in result.episodes] == [
        ("session-001",),
        ("session-002",),
        ("session-003",),
    ]


@pytest.mark.parametrize(("start", "joined"), [(3, True), (4, False)])
def test_one_sided_generic_attachment_is_bounded_to_two_minutes(
    start, joined, make_bundle, make_session, make_slice
) -> None:
    sessions = (
        _repo_session(make_session, make_slice, "session-001", 0, "alpha"),
        _generic_session(make_session, make_slice, "session-002", start),
    )

    result = compact_sessions(_bundle(make_bundle, sessions))

    assert (len(result.episodes) == 1) is joined


@pytest.mark.parametrize(("start", "joined"), [(6, True), (7, False)])
def test_same_anchor_bridge_is_bounded_to_five_minutes(
    start, joined, make_bundle, make_session, make_slice
) -> None:
    sessions = (
        _repo_session(make_session, make_slice, "session-001", 0, "alpha"),
        _repo_session(make_session, make_slice, "session-002", start, "alpha"),
    )

    result = compact_sessions(_bundle(make_bundle, sessions))

    assert (len(result.episodes) == 1) is joined


def test_compaction_aggregates_labels_and_conserves_duration_and_membership(
    make_bundle, make_session, make_slice
) -> None:
    sessions = (
        _repo_session(make_session, make_slice, "session-001", 0, "alpha"),
        _generic_session(make_session, make_slice, "session-002", 2),
        _generic_session(make_session, make_slice, "session-003", 3),
        _repo_session(make_session, make_slice, "session-004", 5, "alpha"),
    )
    source = _bundle(make_bundle, sessions)

    first = compact_sessions(source)
    rebuilt = SessionBundle(
        day=source.day,
        timezone_name=source.timezone_name,
        focused_seconds=source.focused_seconds,
        sessions=tuple(
            session
            for episode in first.episodes
            for session_id in episode.session_ids
            for session in source.sessions
            if session.session_id == session_id
        ),
        diagnostics=source.diagnostics,
    )
    second = compact_sessions(rebuilt)

    assert sum(item.active_seconds for item in first.episodes) == sum(
        item.active_seconds for item in first.sessions
    )
    assert sorted(
        session_id for item in first.episodes for session_id in item.session_ids
    ) == sorted(item.session_id for item in first.sessions)
    assert [(item.value, item.count) for item in first.episodes[0].activity_labels] == [
        ("alpha", 2),
        ("ChatGPT", 2),
    ]
    assert second == first


def test_fractional_durations_survive_regrouping_roundoff(
    make_bundle, make_session, make_slice
) -> None:
    sessions = (
        replace(
            _repo_session(make_session, make_slice, "session-001", 0, "alpha"),
            active_seconds=0.1,
            focused_seconds=0.1,
        ),
        replace(
            _repo_session(make_session, make_slice, "session-002", 10, "beta"),
            active_seconds=0.1,
            focused_seconds=0.1,
        ),
        replace(
            _repo_session(make_session, make_slice, "session-003", 11, "beta"),
            active_seconds=1.1,
            focused_seconds=1.1,
        ),
    )
    source = _bundle(make_bundle, sessions)

    result = compact_sessions(source)

    assert isclose(
        sum(item.active_seconds for item in result.episodes),
        sum(item.active_seconds for item in result.sessions),
        rel_tol=1e-12,
        abs_tol=1e-9,
    )

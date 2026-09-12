from daytrace.episode import compact_sessions
from daytrace.models import ActivitySession, SessionBundle
from daytrace.summarize import build_summary_plan


def test_large_day_compacts_below_single_request_limit(
    make_bundle, make_session, make_slice
) -> None:
    base = make_bundle()
    sessions: list[ActivitySession] = []
    generic = ("ChatGPT", "New tab", "PowerShell", "explorer.exe")
    for index in range(437):
        block = min(index // 88, 4)
        start = index * 0.75
        if index % 11 == 0:
            label = f"project-{block + 1}"
            activity_slice = make_slice(
                start,
                0.5,
                title=label,
                url_host="github.com",
                url_path=f"/fictional/{label}",
                evidence_ids=(f"evidence-{index:04d}",),
            )
        else:
            label = generic[index % len(generic)]
            activity_slice = make_slice(
                start,
                0.5,
                app=label,
                title=label,
                evidence_ids=(f"evidence-{index:04d}",),
            )
        sessions.append(
            make_session(
                session_id=f"session-{index + 1:03d}",
                label=label,
                slices=(activity_slice,),
            )
        )
    fragmented = SessionBundle(
        day=base.day,
        timezone_name=base.timezone_name,
        focused_seconds=sum(item.focused_seconds or 0 for item in sessions),
        sessions=tuple(sessions),
        diagnostics=(),
    )

    compact = compact_sessions(fragmented)
    plan = build_summary_plan(compact)

    assert len(fragmented.sessions) == 437
    assert sum(item.active_seconds < 60 for item in fragmented.sessions) >= 334
    assert len(compact.episodes) <= 80
    assert len(compact.episodes) <= len(fragmented.sessions) * 0.30
    assert len(plan.requests) == 1
    assert plan.requests[0].character_count < 100_000
    assert sum(item.active_seconds for item in compact.episodes) == sum(
        item.active_seconds for item in fragmented.sessions
    )

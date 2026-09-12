from datetime import date

from daytrace.sessionize import sessionize
from daytrace.time import resolve_day


def bundle_for(slices):
    return sessionize(
        date(2026, 9, 10),
        resolve_day(date(2026, 9, 10), "UTC"),
        slices,
        (),
    )


def test_merges_repeated_context_and_bridges_short_interruption(make_slice) -> None:
    first = make_slice(0, 5, title="PerfLife", url_path="/jmoraispk/perflife")
    interruption = make_slice(5, 10 / 60, app="Slack", title="Slack")
    last = make_slice(
        5 + 10 / 60, 5, title="PerfLife", url_path="/jmoraispk/perflife"
    )

    result = bundle_for((first, interruption, last))

    assert len(result.sessions) == 1
    assert result.sessions[0].label == "jmoraispk/perflife"
    assert result.sessions[0].active_seconds == 610


def test_splits_after_idle_gap_and_strong_repository_change(make_slice) -> None:
    perflife = make_slice(0, 5, url_path="/jmoraispk/perflife")
    after_gap = make_slice(11, 5, url_path="/jmoraispk/perflife")
    other_repo = make_slice(16, 5, url_path="/jmoraispk/oai-python")

    result = bundle_for((perflife, after_gap, other_repo))

    assert [item.label for item in result.sessions] == [
        "jmoraispk/perflife",
        "jmoraispk/perflife",
        "jmoraispk/oai-python",
    ]


def test_generic_chatgpt_does_not_inherit_one_sided_context(make_slice) -> None:
    repo = make_slice(0, 5, url_path="/jmoraispk/perflife")
    chatgpt = make_slice(5, 5, app="ChatGPT.exe", title="ChatGPT")

    result = bundle_for((repo, chatgpt))

    assert len(result.sessions) == 2
    assert result.sessions[1].label == "ChatGPT"


def test_detects_bounded_outcome_signals(make_slice) -> None:
    new_repo = make_slice(0, 1, title="New repository", url_host="github.com")
    named_repo = make_slice(
        1, 2, title="jmoraispk/perflife", url_path="/jmoraispk/perflife"
    )
    success = make_slice(
        3, 1, title="Success Page", url_host="ondemand.labcorp.com"
    )
    installer = make_slice(
        4, 1, app="vcxsrv-installer.exe", title="Installation Options"
    )

    result = bundle_for((new_repo, named_repo, success, installer))
    codes = {
        signal.code
        for session in result.sessions
        for signal in session.outcome_signals
    }

    assert codes == {
        "named-repository-appeared",
        "checkout-success",
        "installer-started",
    }

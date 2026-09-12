from daytrace.diagnostics import DiagnosticCollector
from daytrace.fusion import fuse_observations
from daytrace.models import DiagnosticCode, DiagnosticCount, SourceKind


def test_browser_context_enriches_edge_without_adding_duration(make_sanitized) -> None:
    window = make_sanitized(0, 10, app="msedge.exe", title="PerfLife")
    browser = make_sanitized(
        2,
        5,
        evidence_id="evidence-0002",
        kind=SourceKind.BROWSER,
        app=None,
        title="jmoraispk/perflife",
        url_host="github.com",
        url_path="/jmoraispk/perflife",
    )

    slices = fuse_observations((window, browser), lambda code: None)

    assert [(item.start.minute, item.end.minute) for item in slices] == [
        (0, 2),
        (2, 7),
        (7, 10),
    ]
    assert slices[1].contexts[0].url_path == "/jmoraispk/perflife"
    assert sum(item.duration_seconds for item in slices) == 600


def test_editor_context_only_attaches_to_foreground_editor(make_sanitized) -> None:
    terminal = make_sanitized(0, 5, app="WindowsTerminal.exe")
    editor = make_sanitized(
        0,
        5,
        evidence_id="evidence-0002",
        kind=SourceKind.EDITOR,
        app=None,
        project="C:/src/daytrace",
        file="C:/src/daytrace/main.py",
    )

    slices = fuse_observations((terminal, editor), lambda code: None)

    assert slices[0].contexts == ()


def test_conflicting_windows_choose_stable_winner(make_sanitized) -> None:
    diagnostics = DiagnosticCollector()
    later_id = make_sanitized(0, 5, evidence_id="evidence-0002", app="Firefox")
    first_id = make_sanitized(0, 5, evidence_id="evidence-0001", app="Code")

    slices = fuse_observations((later_id, first_id), diagnostics.add)

    assert slices[0].app == "Code"
    assert diagnostics.snapshot() == (
        DiagnosticCount(DiagnosticCode.WINDOW_CONFLICT, 1),
    )


def test_browser_without_window_is_evidence_only(make_sanitized) -> None:
    browser = make_sanitized(
        0,
        5,
        kind=SourceKind.BROWSER,
        app=None,
        url_host="github.com",
        url_path="/jmoraispk/perflife",
    )

    slices = fuse_observations((browser,), lambda code: None)

    assert len(slices) == 1
    assert slices[0].focused is False
    assert slices[0].duration_seconds == 300
    assert slices[0].contexts[0].url_path == "/jmoraispk/perflife"

from daytrace.diagnostics import DiagnosticCollector, diagnostic_messages
from daytrace.models import DiagnosticCode, DiagnosticCount


def test_diagnostics_aggregate_without_event_content() -> None:
    diagnostics = DiagnosticCollector()
    diagnostics.add(DiagnosticCode.NON_POSITIVE_EVENT)
    diagnostics.add(DiagnosticCode.NON_POSITIVE_EVENT)
    diagnostics.add(DiagnosticCode.UNSUPPORTED_BUCKET, 3)

    assert diagnostics.snapshot() == (
        DiagnosticCount(DiagnosticCode.NON_POSITIVE_EVENT, 2),
        DiagnosticCount(DiagnosticCode.UNSUPPORTED_BUCKET, 3),
    )
    assert diagnostic_messages(diagnostics.snapshot()) == (
        "ignored 2 non-positive ActivityWatch events",
        "ignored 3 unsupported ActivityWatch buckets",
    )
    assert "event-id" not in repr(diagnostics.snapshot())

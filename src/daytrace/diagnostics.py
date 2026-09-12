from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from daytrace.models import DiagnosticCode, DiagnosticCount


_MESSAGE = {
    DiagnosticCode.NON_POSITIVE_EVENT: "non-positive ActivityWatch event",
    DiagnosticCode.NAIVE_TIMESTAMP: "event with a naive timestamp",
    DiagnosticCode.UNSUPPORTED_BUCKET: "unsupported ActivityWatch bucket",
    DiagnosticCode.WINDOW_CONFLICT: "conflicting foreground interval",
    DiagnosticCode.SANITIZED_FIELD: "captured field containing private data",
}


class DiagnosticCollector:
    def __init__(self) -> None:
        self._counts: Counter[DiagnosticCode] = Counter()

    def add(self, code: DiagnosticCode, count: int = 1) -> None:
        if count > 0:
            self._counts[code] += count

    def snapshot(self) -> tuple[DiagnosticCount, ...]:
        return tuple(
            DiagnosticCount(code, self._counts[code])
            for code in DiagnosticCode
            if self._counts[code]
        )


def diagnostic_messages(counts: Iterable[DiagnosticCount]) -> tuple[str, ...]:
    return tuple(
        f"ignored {item.count} {_MESSAGE[item.code]}"
        + ("" if item.count == 1 else "s")
        for item in counts
    )

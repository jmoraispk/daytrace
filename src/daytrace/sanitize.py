from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from daytrace.models import (
    ActivityRecord,
    DiagnosticCode,
    SanitizedObservation,
)


EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
EDGE_SUFFIX = re.compile(
    r"\s+and \d+ more pages(?:\s+-.*?)?\s+-\s+Microsoft.? Edge$", re.I
)
SECRET = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._~-]+|"
    r"(?:api[_-]?key|token|code|state)\s*[=:]\s*[A-Za-z0-9._~-]{12,})"
)
AUTH_HOST_PARTS = ("login.", "auth.", "accounts.")
AUTH_PATH_PARTS = (
    "oauth",
    "authorize",
    "callback",
    "signin",
    "challenge",
    "recover",
    "reset",
)


def _safe_path(host: str | None, path: str | None) -> str | None:
    if not host or not path:
        return None
    lowered_host = host.casefold()
    lowered_path = path.casefold()
    if any(lowered_host.startswith(part) for part in AUTH_HOST_PARTS) or any(
        part in lowered_path for part in AUTH_PATH_PARTS
    ):
        return None
    parts = [part for part in path.split("/") if part]
    if lowered_host == "github.com" and len(parts) >= 2:
        return "/" + "/".join(parts[:2])
    if "gitlab" in lowered_host and len(parts) >= 2:
        kept = parts[:2]
        if len(parts) >= 5 and parts[2:4] in (
            ["-", "merge_requests"],
            ["-", "jobs"],
        ):
            kept = parts[:5]
        return "/" + "/".join(kept)
    return None


def _safe_text(
    value: str | None, diagnose: Callable[[DiagnosticCode], None]
) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value)
    compact = " ".join(normalized.replace("\r", " ").replace("\n", " ").split())[
        :500
    ]
    if compact.startswith(("http://", "https://")):
        try:
            host = urlsplit(compact).hostname
        except ValueError:
            host = None
        diagnose(DiagnosticCode.SANITIZED_FIELD)
        return host.casefold() if host else "[redacted-url]"
    cleaned = EDGE_SUFFIX.sub("", EMAIL.sub("[redacted-email]", compact))
    cleaned = SECRET.sub("[redacted-secret]", cleaned)
    if cleaned != compact:
        diagnose(DiagnosticCode.SANITIZED_FIELD)
    return cleaned or None


def sanitize_records(
    records: Iterable[ActivityRecord],
    diagnose: Callable[[DiagnosticCode], None],
) -> tuple[SanitizedObservation, ...]:
    ordered = sorted(records, key=lambda item: (item.start, item.bucket_id, item.event_id))
    sanitized: list[SanitizedObservation] = []
    for index, item in enumerate(ordered, start=1):
        host = item.url_host.casefold()[:253] if item.url_host else None
        sanitized.append(
            SanitizedObservation(
                evidence_id=f"evidence-{index:04d}",
                kind=item.kind,
                start=item.start,
                end=item.end,
                app=_safe_text(item.app, diagnose),
                title=_safe_text(item.title, diagnose),
                project=_safe_text(item.project, diagnose),
                file=_safe_text(item.file, diagnose),
                url_host=host,
                url_path=_safe_path(host, item.url_path),
                language=_safe_text(item.language, diagnose),
            )
        )
    return tuple(sanitized)

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import PurePath, PureWindowsPath
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
    r"\b(?:api[_-]?key|access[_-]?(?:key|token)|code[_-]?challenge|"
    r"session[_-]?state|password[_-]?reset|token|secret|key|code|state)"
    r"\s*[=:]\s*[A-Za-z0-9._~-]{12,})"
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
URL_HOST = (
    r"(?:localhost|\[[0-9a-f:]+\]|(?:\d{1,3}\.){3}\d{1,3}|"
    r"(?:[a-z0-9-]+\.)+[a-z]{2,})"
)
URL_TOKEN = re.compile(
    rf"(?i)(?<![\w@])(?:https?://)?(?:[^\s/@]+:[^\s/@]+@)?"
    rf"{URL_HOST}(?::\d{{1,5}})?(?:/[^\s]*)?"
)


def _url_host(raw: str) -> str:
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        return (urlsplit(candidate).hostname or "[redacted-url]").casefold()
    except ValueError:
        return "[redacted-url]"


def replace_url_tokens(value: str) -> str:
    return URL_TOKEN.sub(lambda match: _url_host(match.group(0)), value)


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
    cleaned = replace_url_tokens(compact)
    cleaned = EDGE_SUFFIX.sub("", EMAIL.sub("[redacted-email]", cleaned))
    cleaned = SECRET.sub("[redacted-secret]", cleaned)
    if cleaned != compact:
        diagnose(DiagnosticCode.SANITIZED_FIELD)
    return cleaned or None


def sanitize_generated_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    compact = " ".join(normalized.replace("\r", " ").replace("\n", " ").split())
    cleaned = replace_url_tokens(compact)
    return SECRET.sub("[redacted-secret]", EMAIL.sub("[redacted-email]", cleaned))


def _safe_path_text(
    value: str | None, diagnose: Callable[[DiagnosticCode], None]
) -> str | None:
    cleaned = _safe_text(value, diagnose)
    if not cleaned:
        return None
    path = (
        PureWindowsPath(cleaned)
        if "\\" in cleaned or ":" in cleaned
        else PurePath(cleaned)
    )
    basename = path.name or None
    if basename != cleaned:
        diagnose(DiagnosticCode.SANITIZED_FIELD)
    return basename


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
                project=_safe_path_text(item.project, diagnose),
                file=_safe_path_text(item.file, diagnose),
                url_host=host,
                url_path=_safe_path(host, item.url_path),
                language=_safe_text(item.language, diagnose),
            )
        )
    return tuple(sanitized)

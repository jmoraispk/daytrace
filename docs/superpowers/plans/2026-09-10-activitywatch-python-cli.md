# ActivityWatch Python CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform Python CLI and importable library that fetches one day of raw ActivityWatch watcher events and renders a deterministic Markdown summary.

**Architecture:** A thin CLI calls a public `summarize_day` function. That function uses an adapter around ActivityWatch's official `aw-client`, converts supported watcher events into immutable domain records, removes AFK intervals, filters and merges records, builds a report without double-counting window time, and renders stable Markdown. The adapter boundary permits unit tests to use synthetic data while a final smoke test exercises the installed ActivityWatch server.

**Tech Stack:** Python 3.11+, `aw-client`, `tzlocal`, conditional `tzdata`, standard-library `argparse`, `uv`, `uv_build`, and `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-10-activitywatch-day-summary-cli-design.md`

## Global Constraints

- Support Python 3.11 or newer on Linux, macOS, and Windows.
- Read ActivityWatch only through the official `aw-client` interface; never open its SQLite files.
- Default to `http://127.0.0.1:5600` and make no network call other than the explicitly configured ActivityWatch server.
- Read only `currentwindow`, `afkstatus`, `web.tab.current`, and `app.editor.activity` buckets; ignore unknown types with a warning.
- Fetch exactly one local calendar day as a half-open interval and discard non-positive clipped records.
- Never print full URLs or URL query strings; browser output contains only the host and title.
- Apply Unicode case-insensitive project matching across project, application, title, file path, URL host, and bucket ID.
- Use current-window data as the only source for active-time and application totals; partition overlapping window records deterministically.
- Given identical inputs and timezone data, output byte-identical Markdown with no generation timestamp or LLM call.
- Write output files as UTF-8 without a BOM and with LF newlines on every operating system.
- Send warnings and errors to stderr while keeping stdout valid Markdown only.
- Publish an importable `daytrace.activitywatch.summarize_day(...) -> str` API and a `daytrace` console script.
- Defer UI, background capture, LLM summaries, GitHub synchronization, automatic second-brain writes, JSON output, and native executables.

## File Map

- `pyproject.toml` — package metadata, Python/dependency constraints, build backend, console entry point, and pytest configuration.
- `uv.lock` — exact development and runtime dependency resolution.
- `.gitignore` — generated Python, test, environment, and distribution artifacts.
- `src/daytrace/__init__.py` — package version export.
- `src/daytrace/__main__.py` — `python -m daytrace` entry point.
- `src/daytrace/cli.py` — argument parsing, stderr/stdout behavior, exit codes, and file output.
- `src/daytrace/models.py` — immutable endpoint, bucket, event, normalized record, and report types.
- `src/daytrace/time.py` — IANA timezone discovery and calendar-day boundary construction.
- `src/daytrace/source.py` — read-only source protocol and `aw-client` adapter.
- `src/daytrace/normalize.py` — supported bucket recognition, event clipping, field extraction, and privacy-safe URL normalization.
- `src/daytrace/transform.py` — AFK subtraction, project filtering, same-bucket merging, interval union, and overlap partitioning.
- `src/daytrace/report.py` — report-model construction and duration allocation.
- `src/daytrace/markdown.py` — deterministic Markdown escaping, formatting, and rendering.
- `src/daytrace/activitywatch.py` — public orchestration API.
- `tests/conftest.py` — reusable synthetic source and record factories.
- `tests/test_cli.py` — command parsing, exit status, stdout/stderr, and output-file behavior.
- `tests/test_time.py` — timezone and daylight-saving boundaries.
- `tests/test_source.py` — server URL parsing and `aw-client` conversion.
- `tests/test_normalize.py` — watcher schemas, clipping, ordering, and privacy normalization.
- `tests/test_transform.py` — AFK, project matching, merge, and overlap algorithms.
- `tests/test_markdown.py` — escaping, duration formatting, and golden Markdown.
- `tests/test_activitywatch.py` — end-to-end library flow with a fake source.
- `tests/golden/daytrace-2026-09-10.md` — byte-for-byte expected report.
- `.github/workflows/ci.yml` — Linux, macOS, and Windows tests plus wheel build.
- `README.md` — source checkout, Windows, published-wheel, error, and second-brain usage.

---

### Task 1: Package Skeleton and Runnable Command

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/daytrace/__init__.py`
- Create: `src/daytrace/__main__.py`
- Create: `src/daytrace/cli.py`
- Create: `tests/test_cli.py`
- Create: `uv.lock`

**Interfaces:**
- Produces: `daytrace.cli.build_parser() -> argparse.ArgumentParser`
- Produces: `daytrace.cli.main(argv: Sequence[str] | None = None) -> int`
- Produces: `daytrace.cli.entrypoint() -> NoReturn`

- [ ] **Step 1: Create the packaging manifest**

```toml
[build-system]
requires = ["uv_build>=0.12.13,<0.13"]
build-backend = "uv_build"

[project]
name = "daytrace"
version = "0.1.0"
description = "Deterministic daily summaries from ActivityWatch"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
dependencies = [
  "aw-client>=0.5.15,<0.6",
  "tzlocal>=5.4,<6",
  "tzdata>=2026.3; sys_platform == 'win32'",
]

[project.scripts]
daytrace = "daytrace.cli:entrypoint"

[dependency-groups]
dev = ["pytest>=9.1,<10"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]
```

Run `uv lock` and confirm it creates `uv.lock` without modifying the declared compatibility ranges.

Create `.gitignore` with:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
dist/
```

- [ ] **Step 2: Write the failing command test**

```python
# tests/test_cli.py
from __future__ import annotations

import subprocess
import sys


def test_module_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "daytrace", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "activitywatch" in result.stdout
    assert result.stderr == ""
```

- [ ] **Step 3: Run the test and verify the expected failure**

Run: `uv run pytest tests/test_cli.py::test_module_help_is_available -v`

Expected: FAIL because `daytrace` does not yet contain an executable module.

- [ ] **Step 4: Add the minimal package and parser**

```python
# src/daytrace/__init__.py
__version__ = "0.1.0"
```

```python
# src/daytrace/cli.py
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import NoReturn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daytrace")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("activitywatch", help="summarize ActivityWatch data")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())
```

```python
# src/daytrace/__main__.py
from daytrace.cli import entrypoint

entrypoint()
```

- [ ] **Step 5: Run the command test and package build**

Run: `uv run pytest tests/test_cli.py::test_module_help_is_available -v`

Expected: PASS.

Run: `uv build --no-sources`

Expected: exit 0 with `dist/daytrace-0.1.0-py3-none-any.whl` and a source archive.

- [ ] **Step 6: Commit the package skeleton**

```bash
git add pyproject.toml uv.lock .gitignore src/daytrace tests/test_cli.py
git commit -m "build: scaffold Python CLI package"
```

---

### Task 2: Domain Models and Calendar-Day Boundaries

**Files:**
- Create: `src/daytrace/models.py`
- Create: `src/daytrace/time.py`
- Create: `tests/test_time.py`

**Interfaces:**
- Produces: `SourceKind`, `ServerEndpoint`, `ServerInfo`, `DayWindow`, `RawBucket`, `RawEvent`, and `ActivityRecord`
- Produces: `resolve_day(day: date, timezone_name: str | None = None) -> DayWindow`
- Consumed later by: source adapter, normalization, transforms, report builder, and public API

- [ ] **Step 1: Write failing timezone tests**

```python
# tests/test_time.py
from datetime import date, timezone

from daytrace.time import resolve_day


def test_resolve_day_builds_half_open_utc_bounds() -> None:
    window = resolve_day(date(2026, 9, 10), "America/Los_Angeles")

    assert window.timezone_name == "America/Los_Angeles"
    assert window.start.astimezone(timezone.utc).isoformat() == "2026-09-10T07:00:00+00:00"
    assert window.end.astimezone(timezone.utc).isoformat() == "2026-09-11T07:00:00+00:00"


def test_resolve_day_preserves_25_hour_dst_day() -> None:
    window = resolve_day(date(2026, 11, 1), "America/Los_Angeles")

    elapsed = window.end.astimezone(timezone.utc) - window.start.astimezone(timezone.utc)
    assert elapsed.total_seconds() == 25 * 60 * 60


def test_resolve_day_uses_discovered_iana_zone(monkeypatch) -> None:
    monkeypatch.setattr("daytrace.time.get_localzone_name", lambda: "Europe/Lisbon")

    window = resolve_day(date(2026, 9, 10))

    assert window.timezone_name == "Europe/Lisbon"
```

- [ ] **Step 2: Run the timezone tests and verify failure**

Run: `uv run pytest tests/test_time.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrace.time'`.

- [ ] **Step 3: Add immutable domain models and timezone resolution**

```python
# src/daytrace/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class SourceKind(StrEnum):
    WINDOW = "current-window"
    AFK = "afk"
    EDITOR = "editor"
    BROWSER = "browser"


@dataclass(frozen=True, slots=True)
class ServerEndpoint:
    protocol: str
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class ServerInfo:
    version: str
    testing: bool


@dataclass(frozen=True, slots=True)
class DayWindow:
    timezone_name: str
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class RawBucket:
    id: str
    type: str
    client: str
    hostname: str


@dataclass(frozen=True, slots=True)
class RawEvent:
    id: str
    timestamp: datetime
    duration_seconds: float
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    event_id: str
    bucket_id: str
    kind: SourceKind
    start: datetime
    end: datetime
    app: str | None = None
    title: str | None = None
    project: str | None = None
    file: str | None = None
    url_host: str | None = None
    language: str | None = None
    status: str | None = None

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def content_key(self) -> tuple[object, ...]:
        return (
            self.bucket_id,
            self.kind,
            self.app,
            self.title,
            self.project,
            self.file,
            self.url_host,
            self.language,
            self.status,
        )
```

```python
# src/daytrace/time.py
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tzlocal import get_localzone_name

from daytrace.models import DayWindow


def resolve_day(day: date, timezone_name: str | None = None) -> DayWindow:
    name = timezone_name or get_localzone_name()
    zone = ZoneInfo(name)
    start = datetime.combine(day, time.min, zone)
    end = datetime.combine(day + timedelta(days=1), time.min, zone)
    return DayWindow(timezone_name=name, start=start, end=end)
```

- [ ] **Step 4: Run timezone tests**

Run: `uv run pytest tests/test_time.py -v`

Expected: 3 tests PASS.

- [ ] **Step 5: Commit domain models and time handling**

```bash
git add src/daytrace/models.py src/daytrace/time.py tests/test_time.py
git commit -m "feat: model ActivityWatch day boundaries"
```

---

### Task 3: Read-Only ActivityWatch Source Adapter

**Files:**
- Create: `src/daytrace/source.py`
- Create: `tests/test_source.py`

**Interfaces:**
- Consumes: `ServerEndpoint`, `ServerInfo`, `RawBucket`, and `RawEvent`
- Produces: `ActivitySource` protocol
- Produces: `parse_server_url(url: str) -> ServerEndpoint`
- Produces: `AwClientSource.from_url(url: str) -> AwClientSource`
- Produces: `AwClientSource.get_info()`, `list_buckets()`, and `get_events(...)`
- Produces: privacy-safe `ActivityWatchConnectionError`

- [ ] **Step 1: Write failing URL and client-conversion tests**

```python
# tests/test_source.py
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from daytrace.models import ServerEndpoint
from daytrace.source import AwClientSource, parse_server_url


def test_parse_server_url_defaults_to_activitywatch_port() -> None:
    assert parse_server_url("http://127.0.0.1") == ServerEndpoint(
        protocol="http", host="127.0.0.1", port=5600
    )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://127.0.0.1:5600",
        "http://user:secret@127.0.0.1:5600",
        "http://127.0.0.1:5600/api",
        "http://127.0.0.1:5600?x=1",
    ],
)
def test_parse_server_url_rejects_ambiguous_or_secret_urls(url: str) -> None:
    with pytest.raises(ValueError, match="ActivityWatch server URL"):
        parse_server_url(url)


def test_adapter_converts_official_client_objects() -> None:
    event = SimpleNamespace(
        id=7,
        timestamp=datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
        duration=timedelta(minutes=5),
        data={"app": "Code", "title": "daytrace"},
    )
    client = SimpleNamespace(
        get_info=lambda: {"version": "v0.13.2 (rust)", "testing": False},
        get_buckets=lambda: {
            "aw-watcher-window_test": {
                "type": "currentwindow",
                "client": "aw-watcher-window",
                "hostname": "test",
            }
        },
        get_events=lambda bucket_id, **kwargs: [event],
    )
    source = AwClientSource(client)

    assert source.get_info().version == "v0.13.2 (rust)"
    assert source.list_buckets()[0].type == "currentwindow"
    assert source.get_events(
        "aw-watcher-window_test",
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        datetime(2026, 9, 11, tzinfo=timezone.utc),
    )[0].duration_seconds == 300
```

- [ ] **Step 2: Run source tests and verify failure**

Run: `uv run pytest tests/test_source.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrace.source'`.

- [ ] **Step 3: Implement the protocol, URL parser, and adapter**

```python
# src/daytrace/source.py
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from aw_client import ActivityWatchClient

from daytrace.models import RawBucket, RawEvent, ServerEndpoint, ServerInfo


class ActivityWatchConnectionError(RuntimeError):
    pass


class ActivitySource(Protocol):
    def get_info(self) -> ServerInfo: ...
    def list_buckets(self) -> tuple[RawBucket, ...]: ...
    def get_events(
        self, bucket_id: str, start: datetime, end: datetime
    ) -> tuple[RawEvent, ...]: ...


def parse_server_url(url: str) -> ServerEndpoint:
    parsed = urlsplit(url)
    valid = (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )
    if not valid:
        raise ValueError("invalid ActivityWatch server URL")
    try:
        port = parsed.port or 5600
    except ValueError as exc:
        raise ValueError("invalid ActivityWatch server URL") from exc
    return ServerEndpoint(parsed.scheme, parsed.hostname, port)


class AwClientSource:
    def __init__(self, client: ActivityWatchClient) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> "AwClientSource":
        endpoint = parse_server_url(url)
        client = ActivityWatchClient(
            "daytrace",
            host=endpoint.host,
            port=endpoint.port,
            protocol=endpoint.protocol,
        )
        return cls(client)

    def get_info(self) -> ServerInfo:
        try:
            info = self._client.get_info()
            return ServerInfo(str(info.get("version", "unknown")), bool(info.get("testing")))
        except Exception as exc:
            raise ActivityWatchConnectionError("ActivityWatch info request failed") from exc

    def list_buckets(self) -> tuple[RawBucket, ...]:
        try:
            buckets = self._client.get_buckets()
            return tuple(
                RawBucket(
                    id=bucket_id,
                    type=str(data.get("type", "")),
                    client=str(data.get("client", "")),
                    hostname=str(data.get("hostname", "")),
                )
                for bucket_id, data in sorted(buckets.items())
            )
        except Exception as exc:
            raise ActivityWatchConnectionError("ActivityWatch bucket request failed") from exc

    def get_events(
        self, bucket_id: str, start: datetime, end: datetime
    ) -> tuple[RawEvent, ...]:
        try:
            events: Sequence[object] = self._client.get_events(
                bucket_id, start=start, end=end
            )
            return tuple(
                RawEvent(
                    id=str(event.id),
                    timestamp=event.timestamp,
                    duration_seconds=(
                        event.duration.total_seconds()
                        if isinstance(event.duration, timedelta)
                        else float(event.duration)
                    ),
                    data=event.data,
                )
                for event in events
            )
        except Exception as exc:
            raise ActivityWatchConnectionError(
                f"ActivityWatch event request failed for bucket {bucket_id!r}"
            ) from exc
```

Do not expose `repr(exc)`, response bodies, event data, credentials, or full URLs in wrapper error messages.

- [ ] **Step 4: Run source tests**

Run: `uv run pytest tests/test_source.py -v`

Expected: all source tests PASS.

- [ ] **Step 5: Commit the read-only adapter**

```bash
git add src/daytrace/source.py tests/test_source.py
git commit -m "feat: add read-only ActivityWatch adapter"
```

---

### Task 4: Watcher Event Normalization

**Files:**
- Create: `src/daytrace/normalize.py`
- Create: `tests/test_normalize.py`

**Interfaces:**
- Consumes: `DayWindow`, `RawBucket`, and `RawEvent`
- Produces: `SUPPORTED_BUCKET_TYPES: Mapping[str, SourceKind]`
- Produces: `normalize_events(bucket, events, window, warn) -> tuple[ActivityRecord, ...]`
- Guarantees: clipped positive-duration records sorted by `(start, bucket_id, event_id)`

- [ ] **Step 1: Write failing watcher-schema and boundary tests**

```python
# tests/test_normalize.py
from datetime import date, datetime, timezone

from daytrace.models import RawBucket, RawEvent, SourceKind
from daytrace.normalize import normalize_events
from daytrace.time import resolve_day


def event(event_id: str, timestamp: str, seconds: float, data: dict[str, object]) -> RawEvent:
    return RawEvent(
        id=event_id,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        duration_seconds=seconds,
        data=data,
    )


def test_normalizes_all_supported_watcher_shapes_without_full_url() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    cases = [
        ("currentwindow", {"app": "Code", "title": "daytrace"}, SourceKind.WINDOW),
        ("afkstatus", {"status": "afk"}, SourceKind.AFK),
        (
            "app.editor.activity",
            {"file": "C:/src/daytrace/main.py", "project": "C:/src/daytrace", "language": "Python"},
            SourceKind.EDITOR,
        ),
        (
            "web.tab.current",
            {"url": "https://docs.activitywatch.net/api?q=secret", "title": "API docs"},
            SourceKind.BROWSER,
        ),
    ]

    records = []
    for index, (bucket_type, data, expected_kind) in enumerate(cases):
        bucket = RawBucket(str(index), bucket_type, "test", "host")
        record = normalize_events(
            bucket,
            [event(str(index), "2026-09-10T12:00:00Z", 60, data)],
            window,
            lambda message: None,
        )[0]
        assert record.kind is expected_kind
        records.append(record)

    assert records[3].url_host == "docs.activitywatch.net"
    assert "secret" not in repr(records[3])


def test_clips_cross_boundary_and_drops_zero_length_records() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("window", "currentwindow", "test", "host")
    warnings: list[str] = []

    records = normalize_events(
        bucket,
        [
            event("cross", "2026-09-09T23:59:00Z", 120, {"app": "Code", "title": "cross"}),
            event("end", "2026-09-11T00:00:00Z", 0, {"app": "Code", "title": "end"}),
        ],
        window,
        warnings.append,
    )

    assert [(record.event_id, record.start, record.duration_seconds) for record in records] == [
        ("cross", datetime(2026, 9, 10, tzinfo=timezone.utc), 60)
    ]
    assert warnings == ["skipped non-positive event 'end' in bucket 'window'"]
```

- [ ] **Step 2: Run normalization tests and verify failure**

Run: `uv run pytest tests/test_normalize.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrace.normalize'`.

- [ ] **Step 3: Implement clipping and known-field extraction**

```python
# src/daytrace/normalize.py
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from daytrace.models import ActivityRecord, DayWindow, RawBucket, RawEvent, SourceKind


ONE_SECOND = timedelta(seconds=1)
SUPPORTED_BUCKET_TYPES: Mapping[str, SourceKind] = {
    "currentwindow": SourceKind.WINDOW,
    "afkstatus": SourceKind.AFK,
    "app.editor.activity": SourceKind.EDITOR,
    "web.tab.current": SourceKind.BROWSER,
}


def _text(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def _url_host(data: Mapping[str, object]) -> str | None:
    value = _text(data, "url")
    if not value:
        return None
    try:
        return urlsplit(value).hostname
    except ValueError:
        return None


def normalize_events(
    bucket: RawBucket,
    events: Iterable[RawEvent],
    window: DayWindow,
    warn: Callable[[str], None],
) -> tuple[ActivityRecord, ...]:
    kind = SUPPORTED_BUCKET_TYPES[bucket.type]
    normalized: list[ActivityRecord] = []
    window_start = window.start.astimezone(timezone.utc)
    window_end = window.end.astimezone(timezone.utc)

    for event in events:
        if event.timestamp.tzinfo is None:
            warn(f"skipped naive timestamp for event {event.id!r} in bucket {bucket.id!r}")
            continue
        raw_start = event.timestamp.astimezone(timezone.utc)
        start = max(raw_start, window_start)
        end = min(raw_start + event.duration_seconds * ONE_SECOND, window_end)
        if end <= start:
            warn(f"skipped non-positive event {event.id!r} in bucket {bucket.id!r}")
            continue
        normalized.append(
            ActivityRecord(
                event_id=event.id,
                bucket_id=bucket.id,
                kind=kind,
                start=start,
                end=end,
                app=_text(event.data, "app"),
                title=_text(event.data, "title"),
                project=_text(event.data, "project"),
                file=_text(event.data, "file"),
                url_host=_url_host(event.data),
                language=_text(event.data, "language"),
                status=_text(event.data, "status"),
            )
        )

    return tuple(sorted(normalized, key=lambda item: (item.start, item.bucket_id, item.event_id)))
```

- [ ] **Step 4: Add invalid-input tests and run normalization tests**

```python
def test_skips_naive_timestamp_with_safe_warning() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("window", "currentwindow", "test", "host")
    warnings: list[str] = []
    naive = RawEvent("naive", datetime(2026, 9, 10, 12), 60, {"app": "Code"})

    assert normalize_events(bucket, (naive,), window, warnings.append) == ()
    assert warnings == ["skipped naive timestamp for event 'naive' in bucket 'window'"]


def test_invalid_browser_url_is_not_retained() -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    bucket = RawBucket("web", "web.tab.current", "test", "host")
    raw = event("bad-url", "2026-09-10T12:00:00Z", 60, {"url": "http://[invalid", "title": "tab"})

    record = normalize_events(bucket, (raw,), window, lambda message: None)[0]

    assert record.url_host is None
    assert "http://[invalid" not in repr(record)
```

Run: `uv run pytest tests/test_normalize.py -v`

Expected: all normalization tests PASS.

- [ ] **Step 5: Commit normalization**

```bash
git add src/daytrace/normalize.py tests/test_normalize.py
git commit -m "feat: normalize ActivityWatch watcher events"
```

---

### Task 5: AFK, Project, Merge, and Overlap Transforms

**Files:**
- Create: `src/daytrace/transform.py`
- Create: `tests/conftest.py`
- Create: `tests/test_transform.py`

**Interfaces:**
- Consumes: sorted `ActivityRecord` values
- Produces: `remove_afk(records) -> tuple[ActivityRecord, ...]`
- Produces: `filter_project(records, project) -> tuple[ActivityRecord, ...]`
- Produces: `merge_adjacent(records, maximum_gap=timedelta(seconds=60)) -> tuple[ActivityRecord, ...]`
- Produces: `partition_window_seconds(records) -> tuple[tuple[ActivityRecord, float], ...]`

- [ ] **Step 1: Add a reusable record factory and failing transform tests**

```python
# tests/conftest.py
from datetime import datetime, timedelta, timezone

import pytest

from daytrace.models import ActivityRecord, SourceKind


@pytest.fixture
def make_record():
    def factory(
        start_minute: int,
        duration_minutes: int,
        *,
        kind: SourceKind = SourceKind.WINDOW,
        bucket: str = "window",
        event_id: str = "1",
        app: str | None = "Code",
        title: str | None = "daytrace",
        project: str | None = None,
        status: str | None = None,
    ) -> ActivityRecord:
        start = datetime(2026, 9, 10, 9, tzinfo=timezone.utc) + timedelta(minutes=start_minute)
        return ActivityRecord(
            event_id=event_id,
            bucket_id=bucket,
            kind=kind,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            app=app,
            title=title,
            project=project,
            status=status,
        )

    return factory
```

```python
# tests/test_transform.py
from dataclasses import replace
from datetime import timedelta

import pytest

from daytrace.models import SourceKind
from daytrace.transform import (
    filter_project,
    merge_adjacent,
    partition_window_seconds,
    remove_afk,
)


def test_remove_afk_splits_active_record(make_record) -> None:
    window = make_record(0, 30)
    away = make_record(10, 5, kind=SourceKind.AFK, bucket="afk", status="afk")

    result = remove_afk((window, away))

    assert [(item.start.minute, item.end.minute) for item in result] == [(0, 10), (15, 30)]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project", "C:/Work/DAYTRACE"),
        ("app", "DAYTRACE Editor"),
        ("title", "Résumé DAYTRACE"),
        ("file", "C:/Work/DAYTRACE/main.py"),
        ("url_host", "DAYTRACE.example"),
        ("bucket_id", "DAYTRACE-window"),
    ],
)
def test_filter_project_uses_unicode_casefold_across_fields(
    make_record, field: str, value: str
) -> None:
    matching = replace(make_record(0, 5, title="unrelated"), **{field: value})
    other = make_record(5, 5, title="mail", project="C:/Personal", event_id="2")

    assert filter_project((matching, other), "daytrace") == (matching,)


def test_merge_adjacent_requires_same_bucket_and_content(make_record) -> None:
    first = make_record(0, 5, event_id="1")
    second = make_record(6, 5, event_id="2")
    other_bucket = make_record(12, 5, event_id="3", bucket="window-2")

    result = merge_adjacent((first, second, other_bucket), timedelta(seconds=60))

    assert [(item.bucket_id, item.start.minute, item.end.minute) for item in result] == [
        ("window", 0, 11),
        ("window-2", 12, 17),
    ]


def test_partition_window_seconds_never_double_counts(make_record) -> None:
    later_bucket = make_record(0, 20, bucket="z-window", app="Firefox")
    first_bucket = make_record(10, 20, bucket="a-window", app="Code")

    allocation = partition_window_seconds((later_bucket, first_bucket))
    totals = {record.app: seconds for record, seconds in allocation}

    assert totals == {"Code": 1200, "Firefox": 600}
    assert sum(totals.values()) == 1800
```

- [ ] **Step 2: Run transform tests and verify failure**

Run: `uv run pytest tests/test_transform.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrace.transform'`.

- [ ] **Step 3: Implement interval transforms**

```python
# src/daytrace/transform.py
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Iterable

from daytrace.models import ActivityRecord, SourceKind


def _sort(records: Iterable[ActivityRecord]) -> tuple[ActivityRecord, ...]:
    return tuple(sorted(records, key=lambda item: (item.start, item.bucket_id, item.event_id)))


def _union(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _subtract_interval(
    fragments: list[tuple[datetime, datetime]],
    away_start: datetime,
    away_end: datetime,
) -> list[tuple[datetime, datetime]]:
    output: list[tuple[datetime, datetime]] = []
    for start, end in fragments:
        if away_end <= start or away_start >= end:
            output.append((start, end))
            continue
        if start < away_start:
            output.append((start, away_start))
        if away_end < end:
            output.append((away_end, end))
    return output


def remove_afk(records: Iterable[ActivityRecord]) -> tuple[ActivityRecord, ...]:
    items = tuple(records)
    away = _union(
        (item.start, item.end)
        for item in items
        if item.kind is SourceKind.AFK and (item.status or "").casefold() == "afk"
    )
    output: list[ActivityRecord] = []
    for item in items:
        if item.kind is SourceKind.AFK:
            continue
        fragments = [(item.start, item.end)]
        for away_start, away_end in away:
            fragments = _subtract_interval(fragments, away_start, away_end)
        output.extend(replace(item, start=start, end=end) for start, end in fragments)
    return _sort(output)


def filter_project(
    records: Iterable[ActivityRecord], project: str | None
) -> tuple[ActivityRecord, ...]:
    if project is None:
        return _sort(records)
    needle = project.casefold()
    return _sort(
        item
        for item in records
        if any(
            needle in value.casefold()
            for value in (
                item.project,
                item.app,
                item.title,
                item.file,
                item.url_host,
                item.bucket_id,
            )
            if value
        )
    )


def merge_adjacent(
    records: Iterable[ActivityRecord],
    maximum_gap: timedelta = timedelta(seconds=60),
) -> tuple[ActivityRecord, ...]:
    output: list[ActivityRecord] = []
    for item in _sort(records):
        if (
            output
            and output[-1].content_key() == item.content_key()
            and item.start - output[-1].end <= maximum_gap
        ):
            output[-1] = replace(output[-1], end=max(output[-1].end, item.end))
        else:
            output.append(item)
    return tuple(output)


def partition_window_seconds(
    records: Iterable[ActivityRecord],
) -> tuple[tuple[ActivityRecord, float], ...]:
    windows = tuple(item for item in records if item.kind is SourceKind.WINDOW)
    boundaries = sorted({point for item in windows for point in (item.start, item.end)})
    totals: dict[ActivityRecord, float] = defaultdict(float)
    for start, end in zip(boundaries, boundaries[1:]):
        candidates = [item for item in windows if item.start < end and item.end > start]
        if candidates:
            winner = min(candidates, key=lambda item: (item.bucket_id, item.event_id))
            totals[winner] += (end - start).total_seconds()
    return tuple(sorted(totals.items(), key=lambda pair: (pair[0].bucket_id, pair[0].event_id)))
```

- [ ] **Step 4: Add concrete edge tests and run the transform suite**

```python
def test_not_afk_does_not_remove_time(make_record) -> None:
    window = make_record(0, 10)
    active = make_record(0, 10, kind=SourceKind.AFK, bucket="afk", status="not-afk")
    assert remove_afk((window, active)) == (window,)


def test_afk_covering_record_removes_it(make_record) -> None:
    window = make_record(5, 5)
    away = make_record(0, 20, kind=SourceKind.AFK, bucket="afk", status="afk")
    assert remove_afk((window, away)) == ()


def test_empty_project_matches_every_record(make_record) -> None:
    records = (make_record(0, 5), make_record(5, 5, event_id="2"))
    assert filter_project(records, "") == records


def test_partition_ignores_non_window_sources(make_record) -> None:
    editor = make_record(0, 30, kind=SourceKind.EDITOR, bucket="editor")
    browser = make_record(0, 30, kind=SourceKind.BROWSER, bucket="web")
    assert partition_window_seconds((editor, browser)) == ()
```

```python
def test_touching_afk_intervals_are_unioned(make_record) -> None:
    window = make_record(0, 30)
    first = make_record(5, 5, kind=SourceKind.AFK, bucket="afk", status="afk")
    second = make_record(10, 5, kind=SourceKind.AFK, bucket="afk", event_id="2", status="afk")
    result = remove_afk((window, first, second))
    assert [(item.start.minute, item.end.minute) for item in result] == [(0, 5), (15, 30)]


def test_overlapping_identical_records_merge_to_later_end(make_record) -> None:
    first = make_record(0, 10, event_id="1")
    second = make_record(5, 10, event_id="2")
    result = merge_adjacent((first, second))
    assert [(item.start.minute, item.end.minute) for item in result] == [(0, 15)]
```

Run: `uv run pytest tests/test_transform.py -v`

Expected: all transform tests PASS.

- [ ] **Step 5: Commit transforms**

```bash
git add src/daytrace/transform.py tests/conftest.py tests/test_transform.py
git commit -m "feat: transform ActivityWatch activity intervals"
```

---

### Task 6: Deterministic Report and Markdown Renderer

**Files:**
- Modify: `src/daytrace/models.py`
- Create: `src/daytrace/report.py`
- Create: `src/daytrace/markdown.py`
- Create: `tests/test_markdown.py`
- Create: `tests/golden/daytrace-2026-09-10.md`

**Interfaces:**
- Produces: `ApplicationTotal`, `ActivityReport`
- Produces: `build_report(day, window, records, project) -> ActivityReport`
- Produces: `format_duration(seconds: float) -> str`
- Produces: `render_markdown(report: ActivityReport) -> str`

- [ ] **Step 1: Add report types to the model contract**

```python
# append to src/daytrace/models.py; add date to the existing datetime import
@dataclass(frozen=True, slots=True)
class ApplicationTotal:
    app: str
    seconds: float


@dataclass(frozen=True, slots=True)
class ActivityReport:
    day: date
    timezone_name: str
    project: str | None
    active_seconds: float | None
    sources: tuple[SourceKind, ...]
    timeline: tuple[ActivityRecord, ...]
    applications: tuple[ApplicationTotal, ...]
```

- [ ] **Step 2: Write the failing golden Markdown test**

```python
# tests/test_markdown.py
from dataclasses import replace
from datetime import date
from pathlib import Path

from daytrace.markdown import render_markdown
from daytrace.models import SourceKind
from daytrace.report import build_report
from daytrace.time import resolve_day


def test_render_markdown_matches_golden_file(make_record) -> None:
    window = resolve_day(date(2026, 9, 10), "UTC")
    window_record = make_record(2, 25, title="daytrace: ActivityWatch client")
    browser_record = replace(
        make_record(
            28,
            13,
            kind=SourceKind.BROWSER,
            bucket="web",
            event_id="2",
            app=None,
            title="ActivityWatch REST API",
        ),
        url_host="docs.activitywatch.net",
    )

    markdown = render_markdown(
        build_report(date(2026, 9, 10), window, (window_record, browser_record), "daytrace")
    )

    expected = Path("tests/golden/daytrace-2026-09-10.md").read_text(encoding="utf-8")
    assert markdown == expected
    assert markdown.endswith("\n")
    assert "http" not in markdown
```

Create `tests/golden/daytrace-2026-09-10.md` with these exact LF-terminated bytes:

```markdown
# Activity summary — 2026-09-10

Project filter: `daytrace`
Timezone: `UTC`

## Overview

- Active matched time: 25m
- Timeline entries: 2
- Sources: Current window, Browser

## Timeline

- 09:02–09:27 (25m) — Code — daytrace: ActivityWatch client
- 09:28–09:41 (13m) — docs.activitywatch.net — ActivityWatch REST API

## Applications

- Code — 25m
```

- [ ] **Step 3: Run the golden test and verify failure**

Run: `uv run pytest tests/test_markdown.py::test_render_markdown_matches_golden_file -v`

Expected: FAIL because `daytrace.report` and `daytrace.markdown` do not exist.

- [ ] **Step 4: Implement report allocation**

```python
# src/daytrace/report.py
from collections import defaultdict
from datetime import date

from daytrace.models import ActivityRecord, ActivityReport, ApplicationTotal, DayWindow, SourceKind
from daytrace.transform import partition_window_seconds


SOURCE_ORDER = {
    SourceKind.WINDOW: 0,
    SourceKind.EDITOR: 1,
    SourceKind.BROWSER: 2,
}


def build_report(
    day: date,
    window: DayWindow,
    records: tuple[ActivityRecord, ...],
    project: str | None,
) -> ActivityReport:
    allocation = partition_window_seconds(records)
    app_seconds: dict[str, float] = defaultdict(float)
    for record, seconds in allocation:
        app_seconds[record.app or "Unknown application"] += seconds
    applications = tuple(
        ApplicationTotal(app, seconds)
        for app, seconds in sorted(
            app_seconds.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
        )
    )
    sources = tuple(sorted({item.kind for item in records}, key=SOURCE_ORDER.__getitem__))
    return ActivityReport(
        day=day,
        timezone_name=window.timezone_name,
        project=project,
        active_seconds=sum(item.seconds for item in applications) if allocation else None,
        sources=sources,
        timeline=records,
        applications=applications,
    )
```

- [ ] **Step 5: Implement stable Markdown rendering**

```python
# src/daytrace/markdown.py
from __future__ import annotations

import html
import re
from zoneinfo import ZoneInfo

from daytrace.models import ActivityRecord, ActivityReport, SourceKind


SOURCE_LABEL = {
    SourceKind.WINDOW: "Current window",
    SourceKind.EDITOR: "Editor",
    SourceKind.BROWSER: "Browser",
}


def format_duration(seconds: float) -> str:
    minutes = max(1, int((seconds + 30) // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours and minutes else f"{hours}h" if hours else f"{minutes}m"


def _single_line(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def _escape(value: str) -> str:
    escaped = html.escape(_single_line(value), quote=False).replace("\\", "\\\\")
    return re.sub(r"([`*_{}\[\]#+|])", r"\\\1", escaped)


def _code(value: str) -> str:
    value = _single_line(value)
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{fence}{padding}{value}{padding}{fence}"


def _basename(value: str | None) -> str | None:
    return value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if value else None


def _label(record: ActivityRecord) -> str:
    if record.kind is SourceKind.WINDOW:
        values = (record.app, record.title)
    elif record.kind is SourceKind.BROWSER:
        values = (record.url_host, record.title)
    else:
        values = (_basename(record.project), _basename(record.file), record.language)
    label = " — ".join(_escape(value) for value in values if value)
    return label or SOURCE_LABEL[record.kind]


def render_markdown(report: ActivityReport) -> str:
    lines = [f"# Activity summary — {report.day.isoformat()}", ""]
    if report.project is not None:
        lines.append(f"Project filter: {_code(report.project)}")
    lines.extend([f"Timezone: {_code(report.timezone_name)}", "", "## Overview", ""])
    if not report.timeline:
        return "\n".join(lines + ["No matching activity.", ""])

    active = format_duration(report.active_seconds) if report.active_seconds is not None else "Unavailable"
    lines.extend(
        [
            f"- Active matched time: {active}",
            f"- Timeline entries: {len(report.timeline)}",
            f"- Sources: {', '.join(SOURCE_LABEL[item] for item in report.sources)}",
            "",
            "## Timeline",
            "",
        ]
    )
    zone = ZoneInfo(report.timezone_name)
    for record in report.timeline:
        start = record.start.astimezone(zone).strftime("%H:%M")
        end = record.end.astimezone(zone).strftime("%H:%M")
        lines.append(f"- {start}–{end} ({format_duration(record.duration_seconds)}) — {_label(record)}")
    if report.applications:
        lines.extend(["", "## Applications", ""])
        lines.extend(f"- {_escape(item.app)} — {format_duration(item.seconds)}" for item in report.applications)
    return "\n".join(lines) + "\n"
```

- [ ] **Step 6: Add formatting, escaping, empty, and timezone tests**

```python
def test_duration_rounding_is_fixed() -> None:
    assert format_duration(1) == "1m"
    assert format_duration(89) == "1m"
    assert format_duration(90) == "2m"
    assert format_duration(3600) == "1h"


def test_empty_report_is_valid_markdown() -> None:
    report = build_report(date(2026, 9, 10), resolve_day(date(2026, 9, 10), "UTC"), (), None)
    assert render_markdown(report).endswith("No matching activity.\n")


def test_non_window_report_marks_active_time_unavailable(make_record) -> None:
    editor = make_record(0, 5, kind=SourceKind.EDITOR, bucket="editor")
    report = build_report(
        date(2026, 9, 10), resolve_day(date(2026, 9, 10), "UTC"), (editor,), None
    )
    assert report.active_seconds is None
    assert report.applications == ()
    assert "Active matched time: Unavailable" in render_markdown(report)


def test_renderer_escapes_markup_and_uses_report_timezone(make_record) -> None:
    record = make_record(7 * 60, 5, title="<script>\n*secret*")
    report = build_report(
        date(2026, 9, 10),
        resolve_day(date(2026, 9, 10), "America/Los_Angeles"),
        (record,),
        None,
    )
    rendered = render_markdown(report)
    assert "<script>" not in rendered
    assert "09:00–09:05" in rendered
    assert rendered == render_markdown(report)
```

Run: `uv run pytest tests/test_markdown.py -v`

Expected: all Markdown tests PASS and the golden file matches byte-for-byte.

- [ ] **Step 7: Commit report rendering**

```bash
git add src/daytrace/models.py src/daytrace/report.py src/daytrace/markdown.py tests/test_markdown.py tests/golden
git commit -m "feat: render deterministic activity Markdown"
```

---

### Task 7: Public Summary API and Complete CLI

**Files:**
- Create: `src/daytrace/activitywatch.py`
- Modify: `src/daytrace/cli.py`
- Create: `tests/test_activitywatch.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `ActivitySource`, `AwClientSource`, normalization, transforms, report builder, and renderer
- Produces: `summarize_day(day, project=None, *, server=..., timezone_name=None, source=None, warn=None) -> str`
- Produces: complete `daytrace activitywatch` command with exit codes 0, 1, and argparse's 2

- [ ] **Step 1: Write a fake source and failing end-to-end library test**

```python
# tests/test_activitywatch.py
from datetime import date, datetime, timezone

from daytrace.activitywatch import summarize_day
from daytrace.models import RawBucket, RawEvent, ServerInfo


class FakeSource:
    def get_info(self) -> ServerInfo:
        return ServerInfo("v0.13.2 (rust)", True)

    def list_buckets(self) -> tuple[RawBucket, ...]:
        return (
            RawBucket("window", "currentwindow", "watcher", "host"),
            RawBucket("afk", "afkstatus", "watcher", "host"),
            RawBucket("ignored", "custom.private", "watcher", "host"),
        )

    def get_events(self, bucket_id, start, end) -> tuple[RawEvent, ...]:
        data = {
            "window": (
                RawEvent(
                    "1",
                    datetime(2026, 9, 10, 9, tzinfo=timezone.utc),
                    600,
                    {"app": "Code", "title": "daytrace"},
                ),
            ),
            "afk": (
                RawEvent(
                    "2",
                    datetime(2026, 9, 10, 9, 5, tzinfo=timezone.utc),
                    120,
                    {"status": "afk"},
                ),
            ),
        }
        return data[bucket_id]


def test_summarize_day_runs_the_complete_pipeline() -> None:
    warnings: list[str] = []

    markdown = summarize_day(
        date(2026, 9, 10),
        "daytrace",
        timezone_name="UTC",
        source=FakeSource(),
        warn=warnings.append,
    )

    assert "Active matched time: 8m" in markdown
    assert "09:00–09:05" in markdown
    assert "09:07–09:10" in markdown
    assert warnings == ["ignored 1 unsupported ActivityWatch bucket"]
```

- [ ] **Step 2: Run the public API test and verify failure**

Run: `uv run pytest tests/test_activitywatch.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'daytrace.activitywatch'`.

- [ ] **Step 3: Implement the public orchestration function**

```python
# src/daytrace/activitywatch.py
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timezone

from daytrace.markdown import render_markdown
from daytrace.normalize import SUPPORTED_BUCKET_TYPES, normalize_events
from daytrace.report import build_report
from daytrace.source import ActivitySource, AwClientSource
from daytrace.time import resolve_day
from daytrace.transform import filter_project, merge_adjacent, remove_afk


DEFAULT_SERVER = "http://127.0.0.1:5600"


def summarize_day(
    day: date,
    project: str | None = None,
    *,
    server: str = DEFAULT_SERVER,
    timezone_name: str | None = None,
    source: ActivitySource | None = None,
    warn: Callable[[str], None] | None = None,
) -> str:
    warning = warn or logging.getLogger("daytrace").warning
    window = resolve_day(day, timezone_name)
    activity_source = source or AwClientSource.from_url(server)
    activity_source.get_info()
    buckets = activity_source.list_buckets()
    supported = tuple(bucket for bucket in buckets if bucket.type in SUPPORTED_BUCKET_TYPES)
    unknown_count = len(buckets) - len(supported)
    if unknown_count:
        noun = "bucket" if unknown_count == 1 else "buckets"
        warning(f"ignored {unknown_count} unsupported ActivityWatch {noun}")

    records = tuple(
        record
        for bucket in supported
        for record in normalize_events(
            bucket,
            activity_source.get_events(
                bucket.id,
                window.start.astimezone(timezone.utc),
                window.end.astimezone(timezone.utc),
            ),
            window,
            warning,
        )
    )
    transformed = merge_adjacent(filter_project(remove_afk(records), project))
    return render_markdown(build_report(day, window, transformed, project))
```

- [ ] **Step 4: Run public API tests**

Run: `uv run pytest tests/test_activitywatch.py -v`

Expected: all public API tests PASS.

- [ ] **Step 5: Write failing CLI behavior tests**

```python
# append to tests/test_cli.py
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from daytrace import cli
from daytrace.source import ActivityWatchConnectionError


def test_cli_writes_utf8_lf_output_file(monkeypatch, tmp_path: Path) -> None:
    markdown = "# Activity summary — 2026-09-10\n"
    monkeypatch.setattr(cli, "summarize_day", lambda *args, **kwargs: markdown)
    output = tmp_path / "summary.md"

    status = cli.main(["activitywatch", "--date", "2026-09-10", "--output", str(output)])

    assert status == 0
    assert output.read_bytes() == markdown.encode("utf-8")


def test_cli_keeps_operational_error_out_of_stdout(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ActivityWatchConnectionError("ActivityWatch info request failed")

    monkeypatch.setattr(cli, "summarize_day", fail)
    status = cli.main(["activitywatch", "--date", "2026-09-10"])

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == (
        "error: ActivityWatch is not reachable at http://127.0.0.1:5600; "
        "start ActivityWatch or pass --server\n"
    )


def test_cli_reports_invalid_timezone_separately(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise ZoneInfoNotFoundError("No time zone found with key Invalid/Zone")

    monkeypatch.setattr(cli, "summarize_day", fail)
    status = cli.main(
        ["activitywatch", "--date", "2026-09-10", "--timezone", "Invalid/Zone"]
    )

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == "error: invalid timezone 'Invalid/Zone'\n"
```

- [ ] **Step 6: Complete CLI parsing and output behavior**

```python
# replace src/daytrace/cli.py
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import NoReturn
from zoneinfo import ZoneInfoNotFoundError

from daytrace.activitywatch import DEFAULT_SERVER, summarize_day
from daytrace.source import ActivityWatchConnectionError


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daytrace")
    commands = parser.add_subparsers(dest="command", required=True)
    activitywatch = commands.add_parser("activitywatch", help="summarize ActivityWatch data")
    activitywatch.add_argument("--date", required=True, type=_date)
    activitywatch.add_argument("--project")
    activitywatch.add_argument("--server", default=DEFAULT_SERVER)
    activitywatch.add_argument("--timezone", dest="timezone_name")
    activitywatch.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        markdown = summarize_day(
            args.date,
            args.project,
            server=args.server,
            timezone_name=args.timezone_name,
            warn=lambda message: print(f"warning: {message}", file=sys.stderr),
        )
    except ZoneInfoNotFoundError:
        print(f"error: invalid timezone {args.timezone_name!r}", file=sys.stderr)
        return 1
    except ValueError:
        print("error: invalid ActivityWatch server URL", file=sys.stderr)
        return 1
    except ActivityWatchConnectionError:
        print(
            f"error: ActivityWatch is not reachable at {args.server}; "
            "start ActivityWatch or pass --server",
            file=sys.stderr,
        )
        return 1

    if args.output:
        try:
            args.output.write_bytes(markdown.replace("\r\n", "\n").encode("utf-8"))
        except OSError:
            print(f"error: could not write output file {str(args.output)!r}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(markdown)
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())
```

Do not include caught exception details or event content in user-facing errors. Add this output failure test:

```python
def test_cli_sanitizes_output_write_failure(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "summarize_day", lambda *args, **kwargs: "summary\n")

    def fail_write(self, data):
        raise OSError("private operating-system detail")

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    output = tmp_path / "summary.md"
    status = cli.main(["activitywatch", "--date", "2026-09-10", "--output", str(output)])

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == f"error: could not write output file {str(output)!r}\n"
    assert "private operating-system detail" not in captured.err
```

- [ ] **Step 7: Run API and CLI tests**

Run: `uv run pytest tests/test_activitywatch.py tests/test_cli.py -v`

Expected: all tests PASS, stdout contains Markdown only, and output bytes use LF.

- [ ] **Step 8: Commit orchestration and CLI**

```bash
git add src/daytrace/activitywatch.py src/daytrace/cli.py tests/test_activitywatch.py tests/test_cli.py
git commit -m "feat: add ActivityWatch summary command"
```

---

### Task 8: Cross-Platform Packaging, Documentation, and Live Smoke Test

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete `daytrace` CLI and wheel
- Produces: documented Windows/source/PyPI workflows and three-OS CI evidence
- Produces: live compatibility evidence against `aw-server-rust` v0.13.2

- [ ] **Step 1: Run the complete local verification suite**

Run: `uv run pytest -v`

Expected: all tests PASS with no skips or warnings owned by Daytrace.

Run: `uv build --no-sources`

Expected: `dist/daytrace-0.1.0-py3-none-any.whl` and `dist/daytrace-0.1.0.tar.gz`.

Run: `uv tool run --from ./dist/daytrace-0.1.0-py3-none-any.whl daytrace --help`

Expected: exit 0 and an `activitywatch` subcommand.

- [ ] **Step 2: Add cross-platform CI**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.11", "3.12", "3.13", "3.14"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
        with:
          version: "0.12.7"
          python-version: ${{ matrix.python }}
      - run: uv sync --frozen --all-groups
      - run: uv run pytest -v
      - run: uv build --no-sources
```

Keep the wheel pure Python. Do not add PyInstaller, Nuitka, platform-specific build artifacts, or release publication in this prototype.

- [ ] **Step 3: Document exact Windows and development usage**

Add a concise quick start to `README.md`, preserving the existing product overview below it:

````markdown
## ActivityWatch summary prototype

Prerequisites: ActivityWatch must be installed and running. Install `uv` on
Windows with:

```powershell
winget install --id=astral-sh.uv -e
```

From a source checkout:

```powershell
git switch codex/activitywatch-integration-research
uv sync
uv run daytrace activitywatch --date 2026-09-10 --output summary.md
```

Filter the report to records containing a project name:

```powershell
uv run daytrace activitywatch --date 2026-09-10 --project daytrace --output summary.md
```

After the package is published, the equivalent one-off command is:

```powershell
uvx daytrace activitywatch --date 2026-09-10 --output summary.md
```

Python callers can use the same deterministic renderer:

```python
from datetime import date
from daytrace.activitywatch import summarize_day

markdown = summarize_day(date(2026, 9, 10), project="daytrace")
```

Daytrace reads ActivityWatch through `http://127.0.0.1:5600` by default. It
does not retain images, audio, video, or a second copy of ActivityWatch events.
````

- [ ] **Step 4: Start a real isolated ActivityWatch v0.13.2 test server**

Run from Bash on this development machine:

```bash
verify_dir=$(mktemp -d /tmp/daytrace-aw-cli.XXXXXX)
aw-server-rust --testing --host 127.0.0.1 --port 5666 \
  --dbpath "$verify_dir/activitywatch.db" --no-legacy-import \
  >"$verify_dir/server.log" 2>&1 &
server_pid=$!
```

Poll `http://127.0.0.1:5666/api/0/info/` every 100 milliseconds for at most five seconds. If it does not become ready, stop and print `server.log`; do not continue against another server.

- [ ] **Step 5: Seed only the isolated server with representative events**

First verify the server is in testing mode:

```bash
curl --fail --silent http://127.0.0.1:5666/api/0/info/ | \
  node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{if(JSON.parse(s).testing!==true)process.exit(1)})'
```

Then create two buckets and their fixed UTC events:

```bash
curl --fail --silent --request POST --header 'Content-Type: application/json' \
  --data '{"type":"currentwindow","client":"daytrace-live-test","hostname":"test-host"}' \
  http://127.0.0.1:5666/api/0/buckets/daytrace-live-window
curl --fail --silent --request POST --header 'Content-Type: application/json' \
  --data '{"type":"afkstatus","client":"daytrace-live-test","hostname":"test-host"}' \
  http://127.0.0.1:5666/api/0/buckets/daytrace-live-afk
curl --fail --silent --request POST --header 'Content-Type: application/json' \
  --data '[{"timestamp":"2026-09-10T16:00:00Z","duration":1800,"data":{"app":"Code","title":"daytrace"}}]' \
  http://127.0.0.1:5666/api/0/buckets/daytrace-live-window/events
curl --fail --silent --request POST --header 'Content-Type: application/json' \
  --data '[{"timestamp":"2026-09-10T16:10:00Z","duration":300,"data":{"status":"afk"}}]' \
  http://127.0.0.1:5666/api/0/buckets/daytrace-live-afk/events
```

Never send these mutation requests to port 5600 or to a server whose `testing` field is false.

- [ ] **Step 6: Run the built CLI against the real server**

Run:

```bash
uv run daytrace activitywatch \
  --server http://127.0.0.1:5666 \
  --timezone America/Los_Angeles \
  --date 2026-09-10 \
  --project daytrace \
  --output "$verify_dir/summary.md"
```

Expected assertions:

```text
exit code: 0
summary contains: # Activity summary — 2026-09-10
summary contains: Active matched time: 25m
summary contains: 09:00–09:10
summary contains: 09:15–09:30
summary does not contain: http://
summary does not contain: https://
```

Run the same command a second time to `summary-2.md`, then run `cmp "$verify_dir/summary.md" "$verify_dir/summary-2.md"`. Expected: exit 0 with no byte differences.

- [ ] **Step 7: Stop the isolated server and verify no listener remains**

Run:

```bash
kill -INT "$server_pid"
wait "$server_pid"
curl --max-time 1 --silent --output /dev/null http://127.0.0.1:5666/api/0/info/
```

Expected: the final `curl` cannot connect. Keep the test database under `/tmp` only until verification is complete; never commit it.

- [ ] **Step 8: Commit documentation and CI**

```bash
git add README.md .github/workflows/ci.yml
git commit -m "docs: add Python CLI quick start and CI"
```

- [ ] **Step 9: Run final verification before branch integration**

Run:

```bash
uv lock --check
uv run pytest -v
uv build --no-sources
git diff --check
git status --short
```

Expected: lockfile current, all tests pass, wheel and source archive build, no whitespace errors, and no uncommitted files other than ignored `dist/` artifacts.

After this evidence is collected, use `superpowers:requesting-code-review`, address any findings, then use `superpowers:finishing-a-development-branch` to choose merge/PR/branch handling. Do not publish to PyPI or merge to `main` until the requested review and verification gates pass.

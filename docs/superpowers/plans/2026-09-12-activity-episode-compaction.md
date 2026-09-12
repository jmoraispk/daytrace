# Activity Episode Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn fragmented ActivityWatch sessions into compact, privacy-minimized activity episodes that support bounded single-pass or hierarchical AI workstream summaries.

**Architecture:** Preserve `ActivitySession` as the fine-grained sanitized audit layer and add a pure compaction layer that produces `EpisodeBundle`. Default Markdown/JSON and provider requests consume episodes; `--raw` still renders sessions and slices. Provider requests remain capped at 100,000 characters per call, partition compact episodes at 80,000 characters, and use a constrained merge pass that can group provisional workstreams but cannot rewrite or strengthen their outcomes.

**Tech Stack:** Python 3.11+, frozen dataclasses, standard-library JSON/URL/path handling, OpenAI Python SDK 2.x Responses API, pytest 9, uv build/publish.

**Spec:** `docs/superpowers/specs/2026-09-12-activity-episode-compaction-design.md`

## Global Constraints

- Canonical project definitions and final project mapping remain in Obsidian.
- Fine-grained sessions remain the lossless sanitized audit representation.
- Episode active and focused duration must exactly conserve session duration.
- Every source session belongs to exactly one episode.
- Every episode belongs to exactly one final workstream or the unassigned set.
- Provider calls receive minimized episodes, never raw events or the full session bundle.
- Provider requests are capped at exactly 100,000 serialized characters and partition toward 80,000 characters.
- Cloud payloads contain no query strings, fragments, emails, credentials, personal names from communication titles, source event IDs, or source bucket IDs.
- A failed AI stage writes the compact deterministic fallback atomically and exits with status 2.
- Existing CLI flags remain accepted.
- CI remains supported on Linux, macOS, and Windows with Python 3.11 through 3.14.
- Completion requires version `0.3.0`, GitHub `main`, tag `v0.3.0`, PyPI wheel/sdist publication, and a clean public `uvx daytrace@latest` smoke test.

## File Structure

- Create `src/daytrace/episode.py`: anchor extraction, generic classification, deterministic episode compaction, and conservation checks.
- Create `src/daytrace/cloud_privacy.py`: stricter provider-only title, URL, path, credential, email, and communication minimization.
- Modify `src/daytrace/models.py`: episode, request-plan, merge, and provider-failure types.
- Modify `src/daytrace/activitywatch.py`: return an `EpisodeBundle` after the existing session pipeline.
- Modify `src/daytrace/markdown.py`: compact episode defaults, raw session audit output, and episode-based digest rendering.
- Modify `src/daytrace/json_output.py`: versioned episode and workstream-report schemas.
- Modify `src/daytrace/summarize.py`: episode request construction, partitioning, chunk validation, merge validation, and deterministic final assembly.
- Modify `src/daytrace/providers/openai.py`: episode/merge schemas and content-free OpenAI error classification.
- Modify `src/daytrace/cli.py`: planned-call disclosure, safe failure messages, and compact fallback behavior.
- Modify `tests/conftest.py`: episode factories and recording providers.
- Create `tests/test_episode.py`: compaction behavior and conservation.
- Create `tests/test_cloud_privacy.py`: provider-view minimization.
- Modify `tests/test_activitywatch.py`, `tests/test_markdown.py`, `tests/test_json_output.py`, `tests/test_summarize.py`, `tests/test_openai_provider.py`, `tests/test_cli.py`, and `tests/test_privacy.py`: pipeline integration and regression coverage.
- Create `tests/test_large_day.py`: synthetic 437-session acceptance fixture.
- Replace affected files in `tests/golden/`: compact deterministic and episode-based AI output.
- Modify `README.md`, `pyproject.toml`, `src/daytrace/__init__.py`, and `uv.lock`: user guidance and `0.3.0` release metadata.

---

### Task 1: Add Episode Types

**Files:**
- Modify: `src/daytrace/models.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_episode.py`

**Interfaces:**
- Consumes: existing `ActivitySession`, `OutcomeSignal`, and `DiagnosticCount`.
- Produces: additive `ActivityAnchor`, `ActivityLabelCount`, `ActivityEpisode`, and `EpisodeBundle` types; existing summary types remain unchanged in this task.

- [ ] **Step 1: Write failing immutable-model tests**

```python
# tests/test_episode.py
from dataclasses import FrozenInstanceError

import pytest


def test_episode_factory_preserves_source_membership(make_episode) -> None:
    episode = make_episode(session_ids=("session-001", "session-002"))

    assert episode.episode_id == "episode-001"
    assert episode.session_ids == ("session-001", "session-002")
    with pytest.raises(FrozenInstanceError):
        episode.label = "changed"
```

Extend `tests/conftest.py` with `make_episode` and `make_episode_bundle` factories. The default episode contains one repository anchor, one application count, one label count, and the existing `session-001`.

- [ ] **Step 2: Run the focused test and verify the missing types fail collection**

Run: `uv run pytest tests/test_episode.py::test_episode_factory_preserves_source_membership -v`

Expected: FAIL during import because `ActivityEpisode` and its supporting types do not exist.

- [ ] **Step 3: Add the exact model types**

```python
# src/daytrace/models.py
@dataclass(frozen=True, slots=True)
class ActivityAnchor:
    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class ActivityLabelCount:
    value: str
    count: int


@dataclass(frozen=True, slots=True)
class ActivityEpisode:
    episode_id: str
    start: datetime
    end: datetime
    active_seconds: float
    focused_seconds: float | None
    label: str
    session_ids: tuple[str, ...]
    anchors: tuple[ActivityAnchor, ...]
    applications: tuple[ActivityLabelCount, ...]
    activity_labels: tuple[ActivityLabelCount, ...]
    outcome_signals: tuple[OutcomeSignal, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EpisodeBundle:
    day: date
    timezone_name: str
    focused_seconds: float | None
    episodes: tuple[ActivityEpisode, ...]
    sessions: tuple[ActivitySession, ...]
    diagnostics: tuple[DiagnosticCount, ...]
```

- [ ] **Step 4: Run the model tests**

Run: `uv run pytest tests/test_episode.py -v && uv run pytest -q`

Expected: the new episode model test and all existing tests pass because this task is additive.

- [ ] **Step 5: Commit the model boundary**

```bash
git add src/daytrace/models.py tests/conftest.py tests/test_episode.py
git commit -m "feat: define compact activity episode models"
```

---

### Task 2: Build the Provider-Only Privacy View

**Files:**
- Create: `src/daytrace/cloud_privacy.py`
- Modify: `src/daytrace/sanitize.py`
- Create: `tests/test_cloud_privacy.py`
- Modify: `tests/test_sanitize.py`
- Modify: `tests/test_privacy.py`

**Interfaces:**
- Consumes: already locally sanitized strings.
- Produces: `minimize_cloud_text(value: str | None) -> str | None`, `minimize_cloud_title(app: str | None, title: str | None) -> str | None`, and `minimize_cloud_path(value: str | None) -> str | None`.

- [ ] **Step 1: Write failing URL and communication minimization tests**

```python
# tests/test_cloud_privacy.py
from daytrace.cloud_privacy import minimize_cloud_path, minimize_cloud_title


def test_cloud_title_removes_embedded_url_query_and_fragment() -> None:
    title = "Authorize https://auth.example/oauth?client_id=abc&state=secret#done"
    assert minimize_cloud_title("Edge", title) == "Authorize auth.example"


def test_cloud_title_removes_direct_message_participant() -> None:
    assert (
        minimize_cloud_title("Slack", "Example Person (DM) - Company - Slack")
        == "Direct message - Slack"
    )


def test_cloud_title_drops_unstructured_meeting_topic() -> None:
    title = "Scheduler requirements | Company | person@example.com | Microsoft Teams"
    assert minimize_cloud_title("Teams", title) == "Meeting - Microsoft Teams"


def test_cloud_path_keeps_only_basename() -> None:
    assert minimize_cloud_path(r"C:\\Users\\person\\private\\report.pdf") == "report.pdf"


def test_local_sanitizer_removes_query_from_scheme_less_url_title(
    make_record
) -> None:
    record = make_record(
        0,
        1,
        title="git.example/oauth/authorize?client_id=public&state=private",
    )
    sanitized = sanitize_records((record,), lambda code: None)
    assert sanitized[0].title == "git.example"
```

- [ ] **Step 2: Verify the new module is missing**

Run: `uv run pytest tests/test_cloud_privacy.py -v`

Expected: FAIL with `ModuleNotFoundError: daytrace.cloud_privacy`.

- [ ] **Step 3: Implement deterministic cloud minimization**

Use `urllib.parse.urlsplit`, the existing `sanitize_generated_text`, and these constants:

```python
URL_TOKEN = re.compile(
    r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}"
    r"(?:/[^\s?#]*)?(?:\?[^\s#]*)?(?:#[^\s]*)?",
    re.I,
)
DIRECT_MESSAGE = re.compile(r"^.*?\s*\(DM\).*?(Slack|Teams).*$", re.I)
COMMUNICATION_APPS = ("slack", "teams", "outlook", "gmail")


def _host_only(match: re.Match[str]) -> str:
    try:
        raw = match.group(0)
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        return (parsed.hostname or "[redacted-url]").casefold()
    except ValueError:
        return "[redacted-url]"


def minimize_cloud_text(value: str | None) -> str | None:
    if not value:
        return None
    replaced = URL_TOKEN.sub(_host_only, value)
    cleaned = sanitize_generated_text(replaced)
    return cleaned[:500] or None
```

Strengthen `sanitize._safe_text` first: recognize an entire URL-shaped title with
or without an `http(s)` scheme, parse it using an added `https://` prefix when
needed, and retain only the lowercase host. This prevents query strings from
appearing even in local default/details/raw Markdown or JSON.

`minimize_cloud_title` returns `Direct message - <surface>` for DM-shaped titles,
reduces mail titles to `Inbox`, `Calendar`, or `Email` plus the application
surface, and reduces unstructured Teams titles to `Meeting - Microsoft Teams`.
The current ActivityWatch title does not structurally distinguish a person's
name from a meeting topic, so arbitrary communication free text is never sent.
A future watcher may retain a separately typed non-personal channel/topic.
Other titles delegate to `minimize_cloud_text`. `minimize_cloud_path` chooses
`PureWindowsPath` or `PurePath` and minimizes only the basename.

- [ ] **Step 4: Extend the end-to-end privacy fixture**

Add window titles containing an embedded OAuth URL and a fictional DM participant. Assert the provider-facing representation omits `client_id`, `state=`, the fictional name, `?`, and `#`, while local raw output still contains the safely sanitized local title.

- [ ] **Step 5: Run privacy tests**

Run: `uv run pytest tests/test_cloud_privacy.py tests/test_sanitize.py tests/test_privacy.py -v && uv run pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit the cloud privacy boundary**

```bash
git add src/daytrace/cloud_privacy.py src/daytrace/sanitize.py tests/test_cloud_privacy.py tests/test_sanitize.py tests/test_privacy.py
git commit -m "feat: minimize cloud-bound activity context"
```

---

### Task 3: Compact Fine-Grained Sessions into Episodes

**Files:**
- Create: `src/daytrace/episode.py`
- Modify: `tests/test_episode.py`

**Interfaces:**
- Consumes: `compact_sessions(bundle: SessionBundle) -> EpisodeBundle` input from the existing sessionizer.
- Produces: ordered episodes with exact source membership, anchor counts, label counts, outcome signals, and durations.

- [ ] **Step 1: Write failing compaction tests**

Add focused tests for all membership rules:

```python
def test_bridges_generic_activity_between_same_repository(make_session_bundle) -> None:
    bundle = make_session_bundle(
        (repo_session("session-001", 0, "alpha"),
         generic_session("session-002", 5, "ChatGPT"),
         repo_session("session-003", 6, "alpha"))
    )

    result = compact_sessions(bundle)

    assert len(result.episodes) == 1
    assert result.episodes[0].session_ids == (
        "session-001", "session-002", "session-003"
    )


def test_does_not_bridge_incompatible_repositories(make_session_bundle) -> None:
    bundle = make_session_bundle(
        (repo_session("session-001", 0, "alpha"),
         generic_session("session-002", 5, "ChatGPT"),
         repo_session("session-003", 6, "beta"))
    )
    result = compact_sessions(bundle)
    assert [episode.session_ids for episode in result.episodes] == [
        ("session-001",), ("session-002",), ("session-003",)
    ]


def test_compaction_conserves_duration_and_membership(make_fragmented_bundle) -> None:
    result = compact_sessions(make_fragmented_bundle())
    assert sum(item.active_seconds for item in result.episodes) == sum(
        item.active_seconds for item in result.sessions
    )
    assert sorted(
        session_id for item in result.episodes for session_id in item.session_ids
    ) == sorted(item.session_id for item in result.sessions)
```

Also test one-sided attachment at two minutes, no attachment beyond two minutes,
same-anchor bridging at five minutes, no bridging beyond five minutes, repeated
label counts, deduplicated outcome signals, stable ordering, and deterministic
output from identical input. The deterministic equality assertion is the
idempotence gate: flatten the produced episodes back to their ordered source
sessions, rebuild the same `SessionBundle`, and assert a second compaction equals
the first.

- [ ] **Step 2: Verify compaction tests fail**

Run: `uv run pytest tests/test_episode.py -v`

Expected: FAIL because `compact_sessions` is unavailable.

- [ ] **Step 3: Implement anchor extraction and compatibility**

Create:

```python
BRIDGE_GAP = timedelta(minutes=5)
ONE_SIDED_GAP = timedelta(minutes=2)
GENERIC_LABELS = {
    "chatgpt", "powershell", "new tab", "inbox", "slack", "outlook",
    "explorer", "explorer.exe", "unknown", "unknown activity",
}
COMMUNICATION_TITLE = re.compile(
    r"(?i)(\(DM\).*Slack|\b(?:Inbox|Calendar).*Outlook|\bMicrosoft Teams$)"
)


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
    priority = {"repository": 0, "project": 1, "file": 2, "title": 3, "domain": 4}
    return tuple(
        sorted(found.values(), key=lambda item: (priority[item.kind], item.value.casefold(), item.value))
    )


def anchors_compatible(
    left: tuple[ActivityAnchor, ...], right: tuple[ActivityAnchor, ...]
) -> bool:
    return bool(
        {(item.kind, item.value.casefold()) for item in left}
        & {(item.kind, item.value.casefold()) for item in right}
    )
```

Anchor priority is repository path, editor project, filename, specific
conversation/document title, then specific domain. Prefix kinds with
`repository`, `project`, `file`, `title`, and `domain`; never compare bare text
from different kinds.

- [ ] **Step 4: Implement grouping and episode construction**

Use a two-pass pure algorithm:

1. Mark each session strong or weak from `session_anchors`.
2. Join strong sessions when compatible and within `BRIDGE_GAP`, consuming only
   intervening weak sessions.
3. Attach remaining weak sessions to one adjacent episode only when within
   `ONE_SIDED_GAP` and no competing strong episode qualifies.
4. Emit remaining contiguous weak sessions as general episodes.

Build episode IDs after final grouping so they remain chronological. Use
`Counter` for applications and labels, and sort counts by `(-count,
value.casefold(), value)`. Choose the label from the first highest-priority
anchor; use an outcome label only for the three existing bounded outcome codes.

At the end of `compact_sessions`, assert exact membership and duration
conservation and raise `EpisodeInvariantError` on violation.

- [ ] **Step 5: Run episode and session tests**

Run: `uv run pytest tests/test_episode.py tests/test_sessionize.py -v && uv run pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit compaction**

```bash
git add src/daytrace/episode.py tests/test_episode.py
git commit -m "feat: compact activity sessions into episodes"
```

---

### Task 4: Make Episodes the Default Local Artifact

**Files:**
- Modify: `src/daytrace/activitywatch.py`
- Modify: `src/daytrace/markdown.py`
- Modify: `src/daytrace/json_output.py`
- Modify: `src/daytrace/cli.py`
- Modify: `tests/test_activitywatch.py`
- Modify: `tests/test_markdown.py`
- Modify: `tests/test_json_output.py`
- Replace: `tests/golden/daytrace-sessions-2026-09-10.md`

**Interfaces:**
- Consumes: `compact_sessions(SessionBundle) -> EpisodeBundle`.
- Produces: `collect_day(day: date, *, server: str = DEFAULT_SERVER, timezone_name: str | None = None, source: ActivitySource | None = None) -> EpisodeBundle`, `render_episode_markdown(bundle, *, details=False, raw=False) -> str`, and `render_episode_json(bundle, *, details=False, raw=False) -> str`.

- [ ] **Step 1: Write failing output tests**

```python
def test_default_markdown_renders_compact_episodes(make_episode_bundle) -> None:
    rendered = render_episode_markdown(make_episode_bundle())
    assert "Summary: Deterministic activity episodes" in rendered
    assert "Activity transitions: 1" in rendered
    assert "session-001" not in rendered


def test_raw_markdown_retains_fine_grained_sessions(make_episode_bundle) -> None:
    rendered = render_episode_markdown(make_episode_bundle(), raw=True)
    assert "## Fine-grained activity" in rendered
    assert "session-001" in rendered


def test_episode_json_uses_new_schema(make_episode_bundle) -> None:
    payload = json.loads(render_episode_json(make_episode_bundle()))
    assert payload["schema"] == "daytrace.episode-bundle.v1"
    assert payload["episodes"][0]["id"] == "episode-001"
    assert "sessions" not in payload
```

Update the CLI test so deterministic mode calls the episode renderer and `--raw`
includes the audit representation.

- [ ] **Step 2: Verify the renderer tests fail**

Run: `uv run pytest tests/test_activitywatch.py tests/test_markdown.py tests/test_json_output.py tests/test_cli.py -v && uv run pytest -q`

Expected: FAIL on missing episode renderer functions and old schema assertions.

- [ ] **Step 3: Wire collection through compaction**

Keep the current acquisition function body through `sessionize`, then return:

```python
sessions = sessionize(day, window, slices, diagnostics.snapshot())
return compact_sessions(sessions)
```

Change `summarize_day` and CLI type flow to accept `EpisodeBundle`.

- [ ] **Step 4: Implement compact Markdown**

Render each episode as one primary bullet with time, label, and exact active
duration. Follow with non-empty indented lines for anchors, tools, transition
count, and outcome signals. `--details` additionally emits episode ID,
source-session IDs, distinct activity-label counts, evidence IDs, and focused
duration. `--raw` appends the existing per-session and per-slice representation
under `## Fine-grained activity`; it does not replace the compact episode list.

- [ ] **Step 5: Implement episode JSON**

Default JSON includes episode ID, start/end, duration, label, typed anchors,
application/label counts, transition count, and outcome signals. `details=True`
adds source-session and evidence IDs. `raw=True` adds the fine-grained session
objects. Keep diagnostics aggregate and content-free.

- [ ] **Step 6: Update golden output and run renderer tests**

Run: `uv run pytest tests/test_activitywatch.py tests/test_markdown.py tests/test_json_output.py tests/test_cli.py -v && uv run pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit the local episode artifact**

```bash
git add src/daytrace/activitywatch.py src/daytrace/markdown.py src/daytrace/json_output.py src/daytrace/cli.py tests/test_activitywatch.py tests/test_markdown.py tests/test_json_output.py tests/test_cli.py tests/golden/daytrace-sessions-2026-09-10.md
git commit -m "feat: render compact activity episodes by default"
```

---

### Task 5: Build Minimized Episode Summary Requests

**Files:**
- Modify: `src/daytrace/models.py`
- Modify: `src/daytrace/summarize.py`
- Modify: `src/daytrace/providers/openai.py`
- Modify: `src/daytrace/markdown.py`
- Modify: `src/daytrace/json_output.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_summarize.py`
- Modify: `tests/test_openai_provider.py`
- Modify: `tests/test_markdown.py`
- Modify: `tests/test_json_output.py`
- Modify: `tests/test_privacy.py`
- Replace: `tests/golden/daytrace-workstreams-2026-09-10.md`

**Interfaces:**
- Consumes: `EpisodeBundle` and cloud-privacy functions.
- Produces: `SummaryPass`, episode-based `SummaryRequest`/`SummaryPlan`, episode-ID workstream models, `build_summary_plan(bundle: EpisodeBundle) -> SummaryPlan`, `validate_digest(payload, allowed_episode_ids) -> WorkstreamDigest`, and schemas `daytrace.summary-request.v2` plus `daytrace.workstream-digest.v2`.

- [ ] **Step 1: Replace session-request tests with episode-request tests**

```python
def test_summary_plan_contains_minimized_episodes(make_episode_bundle) -> None:
    plan = build_summary_plan(make_episode_bundle())
    request = plan.requests[0]
    rendered = json.dumps(request.payload)

    assert request.schema == "daytrace.summary-request.v2"
    assert request.episode_ids == ("episode-001",)
    assert "episodes" in request.payload
    assert "sessions" not in request.payload
    assert "event_id" not in rendered
    assert "bucket_id" not in rendered
    assert plan.planned_request_count == 1
```

Change valid digest fixtures and validation assertions from `session_ids` to
`episode_ids` and from `unassigned_session_ids` to `unassigned_episode_ids`.

- [ ] **Step 2: Verify request tests fail against the v1 builder**

Run: `uv run pytest tests/test_summarize.py tests/test_privacy.py -v`

Expected: FAIL on missing `build_summary_plan` and v2 fields.

- [ ] **Step 3: Implement minimized episode serialization**

First replace the summary model boundary atomically with its consumers:

```python
class SummaryPass(StrEnum):
    CHUNK = "chunk"
    MERGE = "merge"


@dataclass(frozen=True, slots=True)
class WorkstreamSummary:
    label: str
    confidence: Confidence
    episode_ids: tuple[str, ...]
    topics: tuple[TopicSummary, ...]
    outcomes: tuple[OutcomeSummary, ...]


@dataclass(frozen=True, slots=True)
class WorkstreamDigest:
    workstreams: tuple[WorkstreamSummary, ...]
    unassigned_episode_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SummaryRequest:
    schema: str
    pass_kind: SummaryPass
    payload: Mapping[str, object]
    character_count: int
    episode_ids: tuple[str, ...]
    data_categories: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SummaryPlan:
    requests: tuple[SummaryRequest, ...]
    episode_count: int
    input_character_count: int
    planned_request_count: int
    data_categories: tuple[str, ...]
```

Update `make_digest`, `RecordingProvider`, and OpenAI provider's chunk response
format in the same step so no committed state uses mixed session-ID and
episode-ID schemas. Add `make_summary_plan(chunk_count: int = 1,
episode_count: int = 1)` returning exactly `chunk_count` harmless requests.
Update Markdown and JSON digest renderers in the same atomic migration: resolve
`episode_ids` against `bundle.episodes`, compute workstream duration from those
episodes, render compact episode activity, and emit schema
`daytrace.workstream-report.v2`.

Create `_episode_payload` with this exact boundary and return shape:

```python
def _episode_payload(
    episode: ActivityEpisode, categories: set[str]
) -> dict[str, object]:
    payload = {
        "id": episode.episode_id,
        "start": episode.start.isoformat(),
        "end": episode.end.isoformat(),
        "active_seconds": episode.active_seconds,
        "focused_seconds": episode.focused_seconds,
        "label": minimize_cloud_text(episode.label),
        "anchors": [
            {"kind": item.kind, "value": minimize_cloud_text(item.value)}
            for item in episode.anchors
        ],
        "applications": [
            {"value": minimize_cloud_text(item.value), "count": item.count}
            for item in episode.applications
        ],
        "activity_labels": [
            {"value": minimize_cloud_title(None, item.value), "count": item.count}
            for item in episode.activity_labels
        ],
        "transition_count": len(episode.session_ids),
        "outcome_signals": [
            {"code": item.code, "label": minimize_cloud_text(item.label)}
            for item in episode.outcome_signals
        ],
    }
    for field, category in (
        ("anchors", "anchor"),
        ("applications", "application"),
        ("activity_labels", "activity-label"),
        ("outcome_signals", "outcome-signal"),
    ):
        if payload[field]:
            categories.add(category)
    return payload
```

Drop `None` values and duplicate minimized values before JSON serialization.
Compute categories from fields actually retained.

Serialize one group through this focused helper, which is also reused by the
partitioner:

```python
def _request_for_episodes(
    bundle: EpisodeBundle,
    episodes: Sequence[ActivityEpisode],
) -> SummaryRequest:
    categories: set[str] = set()
    payload = {
        "schema": "daytrace.summary-request.v2",
        "prompt_schema": PROMPT_SCHEMA,
        "date": bundle.day.isoformat(),
        "timezone": bundle.timezone_name,
        "focused_seconds": bundle.focused_seconds,
        "episodes": [_episode_payload(item, categories) for item in episodes],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return SummaryRequest(
        schema="daytrace.summary-request.v2",
        pass_kind=SummaryPass.CHUNK,
        payload=payload,
        character_count=len(serialized),
        episode_ids=tuple(item.episode_id for item in episodes),
        data_categories=tuple(
            item for item in CATEGORY_ORDER if item in categories
        ),
    )
```

- [ ] **Step 4: Implement one-request planning and episode validation**

Build a single `SummaryRequest` when serialized payload length is at most
100,000. `validate_digest` accepts an explicit `set[str]` of allowed episode IDs
and enforces exact one-time allocation across workstreams and unassigned IDs.

- [ ] **Step 5: Run summary and privacy tests**

Run: `uv run pytest tests/test_summarize.py tests/test_openai_provider.py tests/test_markdown.py tests/test_json_output.py tests/test_privacy.py -v && uv run pytest -q`

Expected: PASS for one-request flows.

- [ ] **Step 6: Commit episode request v2**

```bash
git add src/daytrace/models.py src/daytrace/summarize.py src/daytrace/providers/openai.py src/daytrace/markdown.py src/daytrace/json_output.py tests/conftest.py tests/test_summarize.py tests/test_openai_provider.py tests/test_markdown.py tests/test_json_output.py tests/test_privacy.py tests/golden/daytrace-workstreams-2026-09-10.md
git commit -m "feat: build minimized episode summary requests"
```

---

### Task 6: Partition Large Days and Merge Provisional Workstreams

**Files:**
- Modify: `src/daytrace/models.py`
- Modify: `src/daytrace/summarize.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_summarize.py`

**Interfaces:**
- Consumes: v2 episode payloads and a provider implementing `summarize(SummaryRequest)` plus `merge(MergeRequest)`.
- Produces: `MergeRequest`, `MergeGroup`, `SummaryProvenance.request_count`, `build_summary_plan`, `build_merge_request`, `validate_merge`, and `summarize_bundle(bundle, provider, plan=None)` with one- or multi-pass behavior.

- [ ] **Step 1: Write failing partition and merge tests**

```python
def test_large_plan_partitions_only_at_episode_boundaries(make_many_episode_bundle) -> None:
    plan = build_summary_plan(
        make_many_episode_bundle(), target_characters=800, max_characters=1000
    )
    assert len(plan.requests) > 1
    assert plan.planned_request_count == len(plan.requests) + 1
    assert all(request.character_count <= 1000 for request in plan.requests)
    assert sorted(
        episode_id for request in plan.requests for episode_id in request.episode_ids
    ) == sorted(
        item.episode_id for item in make_many_episode_bundle().episodes
    )


def test_chunk_merge_cannot_rewrite_or_strengthen_outcomes(
    make_many_episode_bundle, recording_chunk_provider
) -> None:
    digest, provenance = summarize_bundle(
        make_many_episode_bundle(), recording_chunk_provider
    )
    assert provenance.request_count == len(recording_chunk_provider.calls)
    assert digest.workstreams[0].outcomes == (
        recording_chunk_provider.chunk_digests[0].workstreams[0].outcomes
        + recording_chunk_provider.chunk_digests[1].workstreams[0].outcomes
    )
```

Also test an individually oversized episode, oversized merge request, missing or
duplicated provisional IDs, union of chunk-unassigned episode IDs, and summed
token provenance.

- [ ] **Step 2: Verify large-plan tests fail**

Run: `uv run pytest tests/test_summarize.py -k 'large_plan or chunk_merge or oversized or provisional' -v`

Expected: FAIL because partition and merge functions are missing.

- [ ] **Step 3: Implement bounded chronological partitioning**

Add these models before the planning functions and update `make_provenance` to
accept `request_count: int = 1`:

```python
@dataclass(frozen=True, slots=True)
class MergeRequest:
    schema: str
    pass_kind: SummaryPass
    payload: Mapping[str, object]
    character_count: int
    provisional_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MergeGroup:
    label: str
    confidence: Confidence
    provisional_ids: tuple[str, ...]
```

Add `request_count: int` as the final field of `SummaryProvenance` and migrate
all existing constructors in the same change.

Extend the provider protocol at the same boundary:

```python
class SummaryProvider(Protocol):
    def summarize(self, request: SummaryRequest) -> ProviderResponse:
        raise NotImplementedError

    def merge(self, request: MergeRequest) -> ProviderResponse:
        raise NotImplementedError
```

Expose test-only keyword defaults without adding CLI flags:

```python
MAX_REQUEST_CHARACTERS = 100_000
TARGET_REQUEST_CHARACTERS = 80_000


def build_summary_plan(
    bundle: EpisodeBundle,
    *,
    target_characters: int = TARGET_REQUEST_CHARACTERS,
    max_characters: int = MAX_REQUEST_CHARACTERS,
) -> SummaryPlan:
    groups: list[list[ActivityEpisode]] = []
    current: list[ActivityEpisode] = []
    for episode in bundle.episodes:
        candidate = (*current, episode)
        candidate_request = _request_for_episodes(bundle, candidate)
        if current and candidate_request.character_count > target_characters:
            groups.append(current)
            current = [episode]
        else:
            current.append(episode)
        if _request_for_episodes(bundle, current).character_count > max_characters:
            raise EpisodeRequestTooLarge()
    if current:
        groups.append(current)

    requests = tuple(_request_for_episodes(bundle, group) for group in groups)
    if any(request.character_count > max_characters for request in requests):
        raise EpisodeRequestTooLarge()
    categories = tuple(
        sorted({category for request in requests for category in request.data_categories})
    )
    return SummaryPlan(
        requests=requests,
        episode_count=len(bundle.episodes),
        input_character_count=sum(item.character_count for item in requests),
        planned_request_count=len(requests) + (1 if len(requests) > 1 else 0),
        data_categories=categories,
    )
```

Append one whole episode at a time. Before committing an append, serialize the
candidate request. Start a new chunk if it exceeds the target. Raise
`EpisodeRequestTooLarge` if a single-episode request exceeds the maximum. Assert
every produced request is at most the maximum and every episode ID appears once.

- [ ] **Step 4: Define the constrained merge schema**

Each provisional workstream gets a deterministic ID such as
`provisional-001-001`. The merge payload contains provisional ID, label,
confidence, episode IDs, topics, and outcomes. The model may return only:

```json
{
  "schema": "daytrace.workstream-merge.v1",
  "groups": [
    {
      "label": "string",
      "confidence": "high|medium|low",
      "provisional_ids": ["provisional-001-001"]
    }
  ]
}
```

`validate_merge` requires every provisional ID exactly once. Final assembly
unions episode IDs and copies topics/outcomes verbatim from selected provisional
workstreams, deduplicating only exact dataclass equality. Chunk-level unassigned
episode IDs remain final unassigned episode IDs.

- [ ] **Step 5: Implement one- and multi-pass orchestration**

```python
def summarize_bundle(
    bundle: EpisodeBundle,
    provider: SummaryProvider,
    plan: SummaryPlan | None = None,
) -> tuple[WorkstreamDigest, SummaryProvenance]:
    resolved = plan or build_summary_plan(bundle)
    chunk_digests: list[WorkstreamDigest] = []
    responses: list[ProviderResponse] = []
    for request in resolved.requests:
        response = provider.summarize(request)
        responses.append(response)
        chunk_digests.append(
            validate_digest(response.payload, set(request.episode_ids))
        )

    if len(chunk_digests) == 1:
        digest = chunk_digests[0]
    else:
        merge_request, provisional = build_merge_request(tuple(chunk_digests))
        merge_response = provider.merge(merge_request)
        responses.append(merge_response)
        groups = validate_merge(
            merge_response.payload, set(merge_request.provisional_ids)
        )
        digest = assemble_merged_digest(
            groups, provisional, tuple(chunk_digests)
        )

    validate_final_allocation(digest, set(item.episode_id for item in bundle.episodes))
    provenance = SummaryProvenance(
        provider=responses[0].provider,
        model=responses[0].model,
        prompt_schema=PROMPT_SCHEMA,
        input_tokens=_sum_known(item.input_tokens for item in responses),
        output_tokens=_sum_known(item.output_tokens for item in responses),
        request_count=len(responses),
    )
    return digest, provenance
```

Define the neighboring helpers with these exact signatures:

```python
def build_merge_request(
    digests: tuple[WorkstreamDigest, ...],
    *,
    max_characters: int = MAX_REQUEST_CHARACTERS,
) -> tuple[MergeRequest, Mapping[str, WorkstreamSummary]]:
    provisional: dict[str, WorkstreamSummary] = {}
    items: list[dict[str, object]] = []
    for chunk_index, digest in enumerate(digests, start=1):
        for stream_index, workstream in enumerate(digest.workstreams, start=1):
            provisional_id = f"provisional-{chunk_index:03d}-{stream_index:03d}"
            provisional[provisional_id] = workstream
            items.append({
                "id": provisional_id,
                "label": workstream.label,
                "confidence": workstream.confidence.value,
                "episode_ids": list(workstream.episode_ids),
                "topics": [
                    {"text": item.text, "evidence": list(item.evidence)}
                    for item in workstream.topics
                ],
                "outcomes": [
                    {
                        "text": item.text,
                        "strength": item.strength.value,
                        "evidence": list(item.evidence),
                    }
                    for item in workstream.outcomes
                ],
            })
    payload = {
        "schema": "daytrace.workstream-merge-request.v1",
        "provisional_workstreams": items,
    }
    character_count = len(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if character_count > max_characters:
        raise MergeRequestTooLarge()
    request = MergeRequest(
        schema="daytrace.workstream-merge-request.v1",
        pass_kind=SummaryPass.MERGE,
        payload=payload,
        character_count=character_count,
        provisional_ids=tuple(provisional),
    )
    return request, MappingProxyType(provisional)

def validate_merge(
    payload: Mapping[str, object], allowed: set[str]
) -> tuple[MergeGroup, ...]:
    root = _object(payload, "merge response", {"schema", "groups"})
    if root["schema"] != "daytrace.workstream-merge.v1":
        raise SummaryValidationError("invalid merge schema")
    groups: list[MergeGroup] = []
    allocated: list[str] = []
    for index, raw_group in enumerate(_list(root["groups"], "groups", 30)):
        field = f"groups[{index}]"
        value = _object(raw_group, field, {"label", "confidence", "provisional_ids"})
        provisional_ids = _ids(value["provisional_ids"], allowed, f"{field}.provisional_ids")
        allocated.extend(provisional_ids)
        try:
            confidence = Confidence(_bounded_text(value["confidence"], f"{field}.confidence", 20))
        except ValueError:
            raise SummaryValidationError(f"invalid {field}.confidence") from None
        groups.append(MergeGroup(
            label=_bounded_text(value["label"], f"{field}.label", 120),
            confidence=confidence,
            provisional_ids=provisional_ids,
        ))
    if len(allocated) != len(set(allocated)) or set(allocated) != allowed:
        raise SummaryValidationError("invalid provisional allocation")
    return tuple(groups)

def assemble_merged_digest(
    groups: tuple[MergeGroup, ...],
    provisional: Mapping[str, WorkstreamSummary],
    chunks: tuple[WorkstreamDigest, ...],
) -> WorkstreamDigest:
    workstreams: list[WorkstreamSummary] = []
    for group in groups:
        selected = tuple(provisional[item] for item in group.provisional_ids)
        workstreams.append(WorkstreamSummary(
            label=group.label,
            confidence=group.confidence,
            episode_ids=tuple(
                episode_id for item in selected for episode_id in item.episode_ids
            ),
            topics=tuple(dict.fromkeys(
                topic for item in selected for topic in item.topics
            )),
            outcomes=tuple(dict.fromkeys(
                outcome for item in selected for outcome in item.outcomes
            )),
        ))
    unassigned = tuple(dict.fromkeys(
        episode_id
        for chunk in chunks
        for episode_id in chunk.unassigned_episode_ids
    ))
    return WorkstreamDigest(tuple(workstreams), unassigned)
```

For these helper bodies, use the exact merge schema and allocation algorithm in
Step 4: enumerate chunk/workstream pairs into the provisional mapping, require
all mapping keys once in `validate_merge`, concatenate selected episode IDs and
copy dataclass topic/outcome values in `assemble_merged_digest`, then union the
chunks' unassigned episode IDs.

Rename the existing `_session_ids` validator to `_ids` with signature
`_ids(value: object, allowed: set[str], field: str) -> tuple[str, ...]`. Add:

```python
def validate_final_allocation(
    digest: WorkstreamDigest, allowed: set[str]
) -> None:
    allocated = [
        episode_id
        for workstream in digest.workstreams
        for episode_id in workstream.episode_ids
    ] + list(digest.unassigned_episode_ids)
    if len(allocated) != len(set(allocated)) or set(allocated) != allowed:
        raise SummaryValidationError("invalid final episode allocation")


def _sum_known(values: Iterable[int | None]) -> int | None:
    resolved = tuple(values)
    return sum(value for value in resolved if value is not None) if any(
        value is not None for value in resolved
    ) else None
```

For one chunk, validate and return it without `provider.merge`. For multiple
chunks, validate each response against only that chunk's episode IDs, build and
size-check the merge request, call `provider.merge`, validate grouping, assemble
the digest, and validate final episode allocation. Sum input/output tokens from
all provider responses and count every call.

- [ ] **Step 6: Run all summary tests**

Run: `uv run pytest tests/test_summarize.py -v && uv run pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit hierarchical summarization**

```bash
git add src/daytrace/models.py src/daytrace/summarize.py tests/conftest.py tests/test_summarize.py
git commit -m "feat: summarize large days with bounded model passes"
```

---

### Task 7: Support Episode and Merge Requests in the OpenAI Provider

**Files:**
- Modify: `src/daytrace/models.py`
- Modify: `src/daytrace/providers/openai.py`
- Modify: `src/daytrace/providers/__init__.py`
- Modify: `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: `SummaryRequest` and `MergeRequest`.
- Produces: `OpenAIProvider.summarize`, `OpenAIProvider.merge`, and `SummaryProviderError.kind: ProviderFailureKind` without raw SDK text.

- [ ] **Step 1: Write failing provider-format and error-kind tests**

```python
def test_openai_provider_uses_episode_schema(recording_client, summary_request) -> None:
    OpenAIProvider("secret", "model", client=recording_client).summarize(
        summary_request
    )
    call = recording_client.calls[0]
    assert call["text"]["format"]["name"] == "daytrace_workstream_digest_v2"


def test_openai_provider_uses_constrained_merge_schema(
    recording_client, merge_request
) -> None:
    OpenAIProvider("secret", "model", client=recording_client).merge(merge_request)
    call = recording_client.calls[0]
    assert call["text"]["format"]["name"] == "daytrace_workstream_merge_v1"


@pytest.mark.parametrize(
    ("status_code", "error_type", "kind"),
    [
        (401, AuthenticationError, ProviderFailureKind.AUTHENTICATION),
        (429, RateLimitError, ProviderFailureKind.RATE_LIMIT),
        (500, InternalServerError, ProviderFailureKind.SERVICE),
        (400, BadRequestError, ProviderFailureKind.REQUEST),
    ],
)
def test_provider_classifies_status_failure_without_sdk_message(
    status_code, error_type, kind, make_episode_bundle
) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    sdk_error = error_type("private provider detail", response=response, body=None)
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(sdk_error))
    )
    provider = OpenAIProvider("runtime-secret", "model", client=client)

    with pytest.raises(SummaryProviderError) as caught:
        provider.summarize(build_summary_plan(make_episode_bundle()).requests[0])

    assert caught.value.kind is kind
    assert "private provider detail" not in str(caught.value)
    assert "runtime-secret" not in repr(caught.value)


def test_provider_classifies_connection_failure(make_episode_bundle) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    sdk_error = APIConnectionError(request=request)
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(sdk_error))
    )
    provider = OpenAIProvider("runtime-secret", "model", client=client)
    with pytest.raises(SummaryProviderError) as caught:
        provider.summarize(build_summary_plan(make_episode_bundle()).requests[0])
    assert caught.value.kind is ProviderFailureKind.NETWORK
```

- [ ] **Step 2: Verify provider tests fail**

Run: `uv run pytest tests/test_openai_provider.py -v`

Expected: FAIL on v1 schema names, missing merge method, and untyped provider error.

- [ ] **Step 3: Add episode and merge response formats**

Add the provider error taxonomy to `models.py`:

```python
class ProviderFailureKind(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate-limit"
    NETWORK = "network"
    SERVICE = "service"
    REQUEST = "request"
```

Keep the episode-based `daytrace.workstream-digest.v2` format from Task 5 and
add the merge format exactly matching the three-field group objects from Task 6.
Use separate system prompts: the chunk
prompt infers provisional workstreams from minimized episodes; the merge prompt
groups supplied provisional workstreams and explicitly forbids generating
topics, outcomes, evidence, or episode allocations.

- [ ] **Step 4: Add content-free SDK exception classification**

`SummaryProviderError` stores only `ProviderFailureKind` and always has the fixed
message `OpenAI summary request failed`. Map authentication/permission errors,
rate limits, connection/timeouts, server status, and remaining request errors to
the five enum values. Never retain `str(exc)`, response bodies, headers, request
payloads, or the API key.

- [ ] **Step 5: Run provider and privacy tests**

Run: `uv run pytest tests/test_openai_provider.py tests/test_privacy.py -v && uv run pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit provider support**

```bash
git add src/daytrace/models.py src/daytrace/providers/openai.py src/daytrace/providers/__init__.py tests/test_openai_provider.py tests/test_privacy.py
git commit -m "feat: classify and merge OpenAI summary requests"
```

---

### Task 8: Disclose Planned Calls and Report Safe Failure Categories

**Files:**
- Modify: `src/daytrace/cli.py`
- Modify: `src/daytrace/markdown.py`
- Modify: `src/daytrace/json_output.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_markdown.py`
- Modify: `tests/test_json_output.py`
- Replace: `tests/golden/daytrace-workstreams-2026-09-10.md`

**Interfaces:**
- Consumes: `SummaryPlan`, episode-based digest/provenance, and typed summary exceptions.
- Produces: one consent disclosure before any model call, specific safe warnings, compact fallback, episode-based Markdown/JSON digest activity, and exit status 2 on every AI failure.

- [ ] **Step 1: Write failing disclosure and error-message tests**

```python
def test_chunk_disclosure_precedes_key_and_summary_execution(
    monkeypatch, capsys, make_episode_bundle, make_summary_plan,
    make_digest, make_provenance
) -> None:
    calls = []
    plan = make_summary_plan(chunk_count=3, episode_count=437)
    monkeypatch.setattr(cli, "collect_day", lambda *args, **kwargs: make_episode_bundle())
    monkeypatch.setattr(cli, "build_summary_plan", lambda bundle: plan)
    monkeypatch.setattr(
        cli, "input", lambda prompt: calls.append(("confirm", prompt)) or "y"
    )
    monkeypatch.setattr(
        cli.getpass, "getpass", lambda prompt: calls.append(("key", prompt)) or "secret"
    )
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda bundle, key, model, resolved_plan: (
            calls.append(("summary", model)) or (make_digest(), make_provenance(4))
        ),
    )

    status = cli.main([
        "activitywatch", "--date", "2026-09-10", "--summary", "ai",
        "--provider", "openai", "--model", "model",
    ])
    captured = capsys.readouterr()

    assert status == 0
    assert [kind for kind, _ in calls] == ["confirm", "key", "summary"]
    assert "437 compact episodes" in captured.err
    assert "3 summary chunks plus 1 merge call" in captured.err
    assert "total initial input" in captured.err


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (EpisodeRequestTooLarge(), "one compact episode exceeds"),
        (MergeRequestTooLarge(), "compact merge request exceeds"),
        (SummaryProviderError(ProviderFailureKind.AUTHENTICATION), "authentication, access, or billing"),
        (SummaryProviderError(ProviderFailureKind.RATE_LIMIT), "rate limit or quota"),
        (SummaryProviderError(ProviderFailureKind.NETWORK), "network"),
        (SummaryProviderError(ProviderFailureKind.SERVICE), "service unavailable"),
        (SummaryValidationError("invalid"), "invalid structured response"),
    ],
)
def test_ai_failure_is_specific_content_free_and_falls_back(
    failure, message, monkeypatch, capsys, make_episode_bundle, make_summary_plan
) -> None:
    monkeypatch.setattr(cli, "collect_day", lambda *args, **kwargs: make_episode_bundle())
    monkeypatch.setattr(
        cli, "build_summary_plan", lambda bundle: make_summary_plan()
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "runtime-secret")
    monkeypatch.setattr(
        cli,
        "_openai_summary",
        lambda bundle, key, model, plan: (_ for _ in ()).throw(failure),
    )

    status = cli.main([
        "activitywatch", "--date", "2026-09-10", "--summary", "ai",
        "--provider", "openai", "--model", "model", "--yes",
    ])
    captured = capsys.readouterr()

    assert status == 2
    assert message in captured.err
    assert "runtime-secret" not in captured.out + captured.err
    assert "Summary: Deterministic activity episodes" in captured.out
```

Assert each error path writes compact deterministic episodes, returns 2, and
contains none of the fixture's sensitive values.

- [ ] **Step 2: Verify CLI tests fail**

Run: `uv run pytest tests/test_cli.py tests/test_markdown.py tests/test_json_output.py -v && uv run pytest -q`

Expected: FAIL on old disclosure, generic warning, and session-based digest activity.

- [ ] **Step 3: Plan before confirmation and call after key entry**

Build `SummaryPlan` before `_confirm_cloud_send`. Change confirmation to accept
the plan and render singular/plural chunk and merge counts. Only after consent
and hidden key entry instantiate `OpenAIProvider` and call
`summarize_bundle(bundle, provider, plan)`.

- [ ] **Step 4: Map typed failures to fixed messages**

Add a pure `_summary_failure_message(exc: Exception) -> str` returning only the
seven tested messages. Keep captured exception content out of stdout/stderr. The
outer handler always renders the episode fallback and exits 2.

- [ ] **Step 5: Render episode-based workstream activity and provenance**

Resolve `episode_ids` against `bundle.episodes`, calculate durations from
episodes, and render compact episode activity under each workstream. Include
provider request count in Markdown details and JSON summary provenance.

- [ ] **Step 6: Run CLI and renderer tests**

Run: `uv run pytest tests/test_cli.py tests/test_markdown.py tests/test_json_output.py -v && uv run pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit CLI integration**

```bash
git add src/daytrace/cli.py src/daytrace/markdown.py src/daytrace/json_output.py tests/test_cli.py tests/test_markdown.py tests/test_json_output.py tests/golden/daytrace-workstreams-2026-09-10.md
git commit -m "feat: disclose and render episode summary plans"
```

---

### Task 9: Prove High-Fragmentation Acceptance and Cross-Platform Safety

**Files:**
- Create: `tests/test_large_day.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_privacy.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the complete local-to-provider episode pipeline.
- Produces: a synthetic acceptance fixture and documented user workflow.

- [ ] **Step 1: Create the synthetic 437-session fixture**

Generate deterministic fictional sessions across five strong anchors. Between
each anchored session, alternate generic assistant, new-tab, terminal, and file
manager sessions. Make at least 334 sessions shorter than 60 seconds. Include
fictional OAuth-shaped titles, emails, DM titles, repository changes, checkout
success, and installer signals; include no text copied from the user's trace.

- [ ] **Step 2: Write the acceptance test**

```python
def test_large_day_compacts_below_single_request_limit(fragmented_day) -> None:
    compact = compact_sessions(fragmented_day)
    plan = build_summary_plan(compact)

    assert len(fragmented_day.sessions) >= 437
    assert sum(item.active_seconds < 60 for item in fragmented_day.sessions) >= 334
    assert len(compact.episodes) <= 80
    assert len(compact.episodes) <= len(fragmented_day.sessions) * 0.30
    assert len(plan.requests) == 1
    assert plan.requests[0].character_count < 100_000
    assert sum(item.active_seconds for item in compact.episodes) == sum(
        item.active_seconds for item in fragmented_day.sessions
    )
```

Add a second fixture with enough distinct episodes to force multiple chunks and
assert the validated final digest allocates every episode once.

- [ ] **Step 3: Add the full privacy matrix**

Serialize `repr(bundle)`, default/details/raw Markdown, default/details/raw JSON,
every chunk request, merge request, final digest Markdown/JSON, and every safe
error message. Assert cloud artifacts omit all forbidden strings; assert raw
local output never contains raw credentials, emails, query strings, or fragments.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -v`

Expected: all tests pass with the large-day and multi-chunk acceptance tests.

- [ ] **Step 5: Run package and syntax checks**

Run:

```bash
git diff --check
uv run python -m compileall -q src tests
uv build --no-sources
uvx --from twine twine check dist/*
```

Expected: every command exits 0 and wheel/sdist checks report `PASSED`.

- [ ] **Step 6: Update user documentation**

Document that default output is compact and project-neutral, `--raw` retains the
audit trail, large compact days may use disclosed chunk plus merge calls, failure
messages remain content-free, and Obsidian owns canonical project mapping. Add a
Windows example with `uvx daytrace@latest` and optionally `--link-mode=copy` for
cross-filesystem uv caches.

- [ ] **Step 7: Commit acceptance and docs**

```bash
git add tests/test_large_day.py tests/conftest.py tests/test_privacy.py README.md
git commit -m "test: prove compact large-day summaries"
```

---

### Task 10: Version, Publish, and Verify DayTrace 0.3.0

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/daytrace/__init__.py`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: green, clean implementation from Tasks 1-9 and `/home/joao/Documents/.env` containing `UV_PUBLISH_TOKEN` with mode `600`.
- Produces: GitHub `main`, tag `v0.3.0`, PyPI 0.3.0 artifacts, and a verified public CLI.

- [ ] **Step 1: Bump all package versions to 0.3.0**

Use `apply_patch` to change `project.version` and `daytrace.__version__`, then run
`uv lock` so the editable package record becomes `0.3.0`.

- [ ] **Step 2: Run fresh release verification**

Run:

```bash
uv run pytest -v
git diff --check
uv build --no-sources --out-dir dist
uvx --from twine twine check dist/daytrace-0.3.0-*
uvx --refresh --from dist/daytrace-0.3.0-py3-none-any.whl daytrace activitywatch --help
```

Expected: full suite passes, both artifacts pass, and wheel-installed help lists
`--summary`, `--provider`, `--model`, `--details`, `--raw`, and `--diagnostics`.

- [ ] **Step 3: Commit and push main**

```bash
git add pyproject.toml src/daytrace/__init__.py uv.lock
git commit -m "release: prepare 0.3.0"
git fetch origin main
git rev-list --left-right --count origin/main...HEAD
git push origin main
```

Expected: fetch shows remote `main` is an ancestor with no remote-only commits;
push succeeds without force.

- [ ] **Step 4: Require green GitHub CI on the release commit**

Find the `CI` workflow run whose `headSha` equals `git rev-parse HEAD`, waiting
for GitHub to create it when necessary, then run:

```bash
release_sha=$(git rev-parse HEAD)
run_id=""
for attempt in $(seq 1 30); do
  run_id=$(gh run list --workflow CI --branch main --limit 20 \
    --json databaseId,headSha \
    --jq ".[] | select(.headSha == \"$release_sha\") | .databaseId" | head -n 1)
  if [ -n "$run_id" ]; then break; fi
  sleep 2
done
test -n "$run_id"
gh run watch "$run_id" --exit-status
```

Expected: the Linux, macOS, and Windows matrix passes for Python 3.11 through
3.14. Do not publish if the workflow is missing, cancelled, or fails.

- [ ] **Step 5: Publish the exact validated artifacts**

Read `UV_PUBLISH_TOKEN` from `/home/joao/Documents/.env` without printing it,
export it only for the publish process, and run:

```bash
uv publish dist/daytrace-0.3.0-py3-none-any.whl \
  dist/daytrace-0.3.0.tar.gz
```

Expected: PyPI accepts both files. Never echo the token or include it in a
command-line argument.

- [ ] **Step 6: Verify published hashes and public installation**

Poll `https://pypi.org/pypi/daytrace/0.3.0/json` until visible. Compare both
published SHA-256 digests with the exact local files. Then run from `/tmp`:

```bash
uvx --no-cache --no-config --isolated daytrace@latest activitywatch --help
uv run --no-cache --no-project --with 'daytrace==0.3.0' python -c \
  'import daytrace; assert daytrace.__version__ == "0.3.0"'
```

Expected: public help exposes the AI flags and the installed module asserts
version 0.3.0.

- [ ] **Step 7: Tag and verify the release**

```bash
git tag -a v0.3.0 -m "DayTrace 0.3.0"
git push origin refs/tags/v0.3.0
git ls-remote origin refs/heads/main refs/tags/v0.3.0 'refs/tags/v0.3.0^{}'
git status --porcelain=v1
```

Expected: remote main and the dereferenced tag point to the release commit, and
the worktree is clean.

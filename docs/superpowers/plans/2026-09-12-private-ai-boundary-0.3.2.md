# Private AI Boundary 0.3.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish DayTrace 0.3.2 with structural URL sanitization, non-persisted OpenAI calls, stricter request-specific output schemas, and useful content-free AI failure diagnostics.

**Architecture:** Centralize URL recognition and secret detection in `sanitize.py`, then use those primitives both during ActivityWatch sanitization and at the final OpenAI egress boundary. Keep model output private while enriching typed validation failures with stable codes, safe request/response metadata, and an opt-in redacted support artifact. Do not alter episode compaction in this release; the sanitized session capture produced by 0.3.2 is the input required to design and verify 0.4.0.

**Tech Stack:** Python 3.11+, standard-library `re`, `urllib.parse`, dataclasses, JSON, OpenAI Python SDK 2.x Responses API, pytest 9, `uv_build`, and PyPI trusted/token publication.

**Spec:** `docs/superpowers/specs/2026-09-12-private-reliable-ai-pipeline-design.md`

## Global Constraints

- Work directly on `main` as requested; do not create a worktree or feature branch.
- Never commit the supplied personal Markdown or JSON trace.
- Never print, persist, or pass an API key in command-line arguments.
- Provider request and response bodies remain memory-only and absent from support artifacts.
- Every OpenAI Responses API call sets `store=False`.
- Local and cloud sanitization remove URL userinfo, port, query, and fragment from DNS, IPv4, IPv6, and localhost URL-shaped text.
- A final content-free privacy assertion runs before the provider client is invoked.
- Existing Markdown and JSON report schema identifiers remain unchanged in 0.3.2.
- Failed AI mode still atomically writes the deterministic fallback and returns status 2.
- CI remains supported on Linux, macOS, and Windows with Python 3.11 through 3.14.
- Completion requires version `0.3.2`, a clean full test run, wheel and source archive inspection, `main` pushed, PyPI published, tag `v0.3.2` pushed, and a clean public `uvx daytrace@0.3.2` smoke test.

## File Structure

- Modify `src/daytrace/sanitize.py`: shared URL-token recognition, host-only replacement, expanded credential assignments, and recursive cloud-safety predicates.
- Modify `src/daytrace/cloud_privacy.py`: consume the shared structural sanitizer and expose `assert_cloud_safe_payload` plus `CloudPrivacyError`.
- Modify `src/daytrace/models.py`: safe provider response metadata and a typed summary-failure report.
- Modify `src/daytrace/providers/openai.py`: request-specific structured-output schemas, `store=False`, and response/request ID capture.
- Modify `src/daytrace/summarize.py`: stable validation codes/paths and failure-context enrichment at chunk and merge boundaries.
- Create `src/daytrace/summary_diagnostics.py`: privacy-safe response-shape projection and versioned support JSON rendering.
- Modify `src/daytrace/cli.py`: `--debug-output`, validation, safe warning detail, and atomic support-artifact writing.
- Modify `tests/test_sanitize.py` and `tests/test_cloud_privacy.py`: URL and credential regressions.
- Modify `tests/test_openai_provider.py`: egress assertion, retention, dynamic schema, and metadata coverage.
- Modify `tests/test_summarize.py`: validation-code and context coverage.
- Create `tests/test_summary_diagnostics.py`: prove support artifacts omit all captured/generated prose and unknown identifiers.
- Modify `tests/test_cli.py`: debug flag validation, fallback behavior, and atomic output.
- Modify `tests/test_privacy.py`: end-to-end forbidden-value checks.
- Modify `README.md`: safe failure and `--debug-output` usage, provider retention, and sanitized recapture command.
- Modify `pyproject.toml`, `src/daytrace/__init__.py`, and `uv.lock`: release version 0.3.2.

---

### Task 1: Structural URL and Secret Sanitization

**Files:**
- Modify: `src/daytrace/sanitize.py`
- Modify: `src/daytrace/cloud_privacy.py`
- Modify: `tests/test_sanitize.py`
- Modify: `tests/test_cloud_privacy.py`
- Modify: `tests/test_privacy.py`

**Interfaces:**
- Consumes: arbitrary ActivityWatch text and already-sanitized episode strings.
- Produces: `replace_url_tokens(value: str) -> str` and the existing
  `minimize_cloud_text`, `minimize_cloud_title`, and `sanitize_records`
  behavior with stronger URL coverage.

- [x] **Step 1: Add failing local URL sanitization cases**

Add parameterized tests using synthetic values only:

```python
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("http://127.0.0.1:8765/setup?key=" + "a" * 40, "127.0.0.1"),
        ("10.20.30.40:63590/?token=" + "b" * 40, "10.20.30.40"),
        ("http://localhost:5173/path?state=" + "c" * 40, "localhost"),
        ("http://[2001:db8::1]:8080/path?secret=" + "d" * 40, "2001:db8::1"),
        ("Open http://127.0.0.1:9000/?key=" + "e" * 40, "Open 127.0.0.1"),
    ],
)
def test_local_sanitizer_strips_every_url_private_component(
    title, expected, make_record
) -> None:
    record = make_record(0, 1, title=title)
    sanitized = sanitize_records((record,), lambda code: None)
    assert sanitized[0].title == expected
    assert "?" not in sanitized[0].title
```

Also extend credential tests with `key=`, `secret=`, `access_token=`, and
`access-key=` followed by 40 synthetic characters.

- [x] **Step 2: Add failing cloud minimization cases**

```python
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Visit 127.0.0.1:8765/?key=" + "a" * 40, "Visit 127.0.0.1"),
        ("localhost:5173/#token=" + "b" * 40, "localhost"),
        ("https://user:pass@example.test:9443/a?q=x#f", "example.test"),
    ],
)
def test_cloud_text_structurally_removes_url_private_parts(value, expected) -> None:
    assert minimize_cloud_text(value) == expected
```

- [x] **Step 3: Run the focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_sanitize.py tests/test_cloud_privacy.py tests/test_privacy.py -v
```

Expected: IPv4/localhost/IPv6 and generic-key cases fail because the current URL regular expressions require a dotted DNS hostname and the current secret expression does not recognize generic `key`.

- [x] **Step 4: Centralize URL recognition in `sanitize.py`**

Replace the separate whole-URL assumptions with one URL-token pattern and safe host parser. The implementation must use named helpers so local and cloud policies cannot drift:

```python
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
```

Apply `replace_url_tokens` before email and secret substitution in `_safe_text`
and `sanitize_generated_text`. Expand `SECRET` to recognize
`key`, `secret`, `access_token`, and `access-key`, while retaining the existing
minimum opaque-value length to avoid redacting ordinary prose.

- [x] **Step 5: Reuse the shared sanitizer in `cloud_privacy.py`**

Delete its independent `URL_TOKEN` and `_host_only`. Implement:

```python
def minimize_cloud_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = sanitize_generated_text(value)
    return cleaned[:500] or None
```

Keep the communication-title and basename policies unchanged.

- [x] **Step 6: Run focused and full privacy tests**

Run:

```bash
uv run pytest tests/test_sanitize.py tests/test_cloud_privacy.py tests/test_privacy.py -v
uv run pytest -q
```

Expected: all URL variants become host-only, synthetic secret values are absent from representations, and the full suite passes.

- [x] **Step 7: Commit the sanitizer boundary**

```bash
git add src/daytrace/sanitize.py src/daytrace/cloud_privacy.py tests/test_sanitize.py tests/test_cloud_privacy.py tests/test_privacy.py
git commit -m "fix: sanitize local service URL credentials"
```

---

### Task 2: Fail-Closed Provider Egress and Non-Persisted Responses

**Files:**
- Modify: `src/daytrace/cloud_privacy.py`
- Modify: `src/daytrace/providers/openai.py`
- Modify: `src/daytrace/models.py`
- Modify: `tests/test_cloud_privacy.py`
- Modify: `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: `SummaryRequest.payload` or `MergeRequest.payload` immediately before SDK invocation.
- Produces: `CloudPrivacyError(code: str = "unsafe-cloud-payload")`,
  `assert_cloud_safe_payload(payload: object) -> None`, optional
  `ProviderResponse.response_id` / `request_id` fields, and optional safe
  `SummaryProviderError.request_id` metadata.

- [x] **Step 1: Add failing recursive egress-assertion tests**

```python
def test_cloud_assertion_rejects_nested_url_query_without_echoing_value() -> None:
    private = "http://localhost:8000/?key=" + "x" * 40
    with pytest.raises(CloudPrivacyError, match="unsafe-cloud-payload") as caught:
        assert_cloud_safe_payload({"episodes": [{"title": private}]})
    assert private not in str(caught.value)


def test_cloud_assertion_allows_natural_question_punctuation() -> None:
    assert_cloud_safe_payload({"title": "What changed? Review the result."})
```

- [x] **Step 2: Add failing provider retention and no-call tests**

Extend the recording-client test to assert:

```python
assert calls[0]["store"] is False
assert result.response_id == "resp_test"
assert result.request_id == "req_test"
```

Give the fake response `id="resp_test"` and `_request_id="req_test"`. Add a second test that builds a `SummaryRequest` containing a nested unsafe URL and proves `client.responses.create` is never called.

- [x] **Step 3: Run tests and verify failure**

Run:

```bash
uv run pytest tests/test_cloud_privacy.py tests/test_openai_provider.py -v
```

Expected: missing assertion API, missing `store`, and missing metadata fields fail.

- [x] **Step 4: Implement recursive privacy assertion**

In `cloud_privacy.py`, define a content-free exception and walk mappings and non-string sequences:

```python
class CloudPrivacyError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("unsafe-cloud-payload")


def assert_cloud_safe_payload(value: object) -> None:
    if isinstance(value, str):
        if sanitize_generated_text(value) != value:
            raise CloudPrivacyError()
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            assert_cloud_safe_payload(key)
            assert_cloud_safe_payload(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            assert_cloud_safe_payload(item)
```

This relies on Task 1's structural URL replacement, so a query-bearing URL
changes under `sanitize_generated_text` and fails closed. The exception contains
no offending key, index, or value.

- [x] **Step 5: Add safe provider metadata and disable storage**

Extend `ProviderResponse` without breaking existing positional callers:

```python
@dataclass(frozen=True, slots=True)
class ProviderResponse:
    payload: Mapping[str, object]
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    response_id: str | None = None
    request_id: str | None = None
```

In `OpenAIProvider._request`, call `assert_cloud_safe_payload(payload)` outside
the SDK exception wrapper, pass `store=False`, and copy only bounded opaque IDs:

```python
response = self._client.responses.create(
    model=self._model,
    instructions=instructions,
    input=json.dumps(payload, ensure_ascii=False, sort_keys=True),
    text={"format": response_format},
    store=False,
)
```

Use a helper that accepts only strings matching `^[A-Za-z0-9_-]{1,200}$` before
placing `response.id` or `response._request_id` in `ProviderResponse`.
Apply the same helper to an SDK exception's `request_id` before retaining it on
`SummaryProviderError`; never retain the SDK message or response body.

- [x] **Step 6: Verify focused and full tests**

Run:

```bash
uv run pytest tests/test_cloud_privacy.py tests/test_openai_provider.py -v
uv run pytest -q
```

Expected: unsafe payloads fail before the fake client call, all calls set
`store=False`, safe opaque IDs are retained, and private exception text remains absent.

- [x] **Step 7: Commit provider privacy behavior**

```bash
git add src/daytrace/cloud_privacy.py src/daytrace/providers/openai.py src/daytrace/models.py tests/test_cloud_privacy.py tests/test_openai_provider.py
git commit -m "fix: prevent persisted or unsafe AI requests"
```

---

### Task 3: Request-Specific OpenAI Schemas

**Files:**
- Modify: `src/daytrace/providers/openai.py`
- Modify: `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: `SummaryRequest.episode_ids` and `MergeRequest.provisional_ids`.
- Produces: `workstream_json_format(episode_ids: tuple[str, ...]) -> dict[str, object]` and `merge_json_format(provisional_ids: tuple[str, ...]) -> dict[str, object]`.

- [x] **Step 1: Add failing schema tests**

```python
def test_summary_schema_restricts_nonempty_ids_to_request(make_episode_bundle) -> None:
    request = build_summary_plan(make_episode_bundle()).requests[0]
    schema = workstream_json_format(request.episode_ids)["schema"]
    item = schema["properties"]["workstreams"]["items"]
    assert item["properties"]["episode_ids"]["minItems"] == 1
    assert item["properties"]["episode_ids"]["items"]["enum"] == ["episode-001"]
    assert item["properties"]["topics"]["items"]["properties"]["evidence"]["minItems"] == 1


def test_merge_schema_restricts_nonempty_ids_to_request(make_digest) -> None:
    request, _ = build_merge_request((make_digest(),))
    schema = merge_json_format(request.provisional_ids)["schema"]
    ids = schema["properties"]["groups"]["items"]["properties"]["provisional_ids"]
    assert ids["minItems"] == 1
    assert ids["items"]["enum"] == ["provisional-001-001"]
```

Also assert the recording client receives the generated format rather than a
module-level mutable schema.

- [x] **Step 2: Run the provider tests and verify failure**

Run: `uv run pytest tests/test_openai_provider.py -v`

Expected: the format-builder imports fail and current schemas lack `minItems`
and request-specific enums.

- [x] **Step 3: Replace constants with pure schema builders**

Build a fresh dictionary per request. Use the request IDs as string enums for
workstream allocation, topic evidence, outcome evidence, unassigned IDs, and
merge provisional IDs. Add `minItems: 1` to workstream `episode_ids`, topic and
outcome `evidence`, and group `provisional_ids`; leave workstreams, topics,
outcomes, groups, and unassigned arrays allowed to be empty.

Do not add `uniqueItems`: it is outside the currently documented strict
Structured Outputs subset and duplicates remain a local semantic check.

For an empty allowed-ID tuple, omit the empty enum and constrain root
`workstreams` plus `unassigned_episode_ids` to `maxItems: 0`; for an empty merge
tuple, constrain root `groups` to `maxItems: 0`. This preserves current empty-day
behavior without emitting a provider-invalid empty enum.

- [x] **Step 4: Route provider methods through builders**

```python
def summarize(self, request: SummaryRequest) -> ProviderResponse:
    return self._request(
        request.payload,
        SYSTEM_PROMPT,
        workstream_json_format(request.episode_ids),
    )


def merge(self, request: MergeRequest) -> ProviderResponse:
    return self._request(
        request.payload,
        MERGE_SYSTEM_PROMPT,
        merge_json_format(request.provisional_ids),
    )
```

- [x] **Step 5: Verify provider and summary integration tests**

Run:

```bash
uv run pytest tests/test_openai_provider.py tests/test_summarize.py -v
uv run pytest -q
```

Expected: generated schemas use only supplied IDs and all tests pass.

- [x] **Step 6: Commit schema alignment**

```bash
git add src/daytrace/providers/openai.py tests/test_openai_provider.py tests/test_summarize.py
git commit -m "fix: constrain AI summaries to supplied evidence"
```

---

### Task 4: Stable Semantic Validation Diagnostics

**Files:**
- Modify: `src/daytrace/models.py`
- Modify: `src/daytrace/summarize.py`
- Modify: `tests/test_summarize.py`

**Interfaces:**
- Consumes: untrusted structured provider payloads and the request whose IDs they must allocate.
- Produces: `SummaryFailureContext`, `SummaryValidationError(code, field, context=None)`, and content-free context enrichment around each chunk/merge validator call.

- [x] **Step 1: Add failing code/path tests**

Update invalid-response tests to assert exact metadata without asserting private values:

```python
with pytest.raises(SummaryValidationError) as caught:
    validate_digest(payload, {"episode-001"})
assert caught.value.code == "empty-evidence"
assert caught.value.field == "workstreams[0].topics[0].evidence"
```

Add cases for:

- empty workstream IDs: `empty-ids`;
- duplicate IDs within one list: `duplicate-ids`;
- unknown IDs: `unknown-ids`;
- incomplete or duplicated final allocation: `invalid-episode-allocation`;
- invalid response object shape: `invalid-shape`;
- wrong schema constant: `invalid-schema`.

- [x] **Step 2: Add failing chunk-context test**

Use a fake provider returning an invalid digest with safe response metadata and
assert the raised error has:

```python
assert caught.value.context.stage is SummaryPass.CHUNK
assert caught.value.context.call_index == 1
assert caught.value.context.request_character_count == plan.requests[0].character_count
assert caught.value.context.item_ids == plan.requests[0].episode_ids
assert caught.value.context.response_id == "resp_test"
assert caught.value.context.request_id == "req_test"
```

Add the corresponding multi-chunk merge case with `SummaryPass.MERGE`.

- [x] **Step 3: Run tests and verify failure**

Run: `uv run pytest tests/test_summarize.py -v`

Expected: current exceptions expose only a prose message and no typed context.

- [x] **Step 4: Add typed failure context**

In `models.py`:

```python
@dataclass(frozen=True, slots=True)
class SummaryFailureContext:
    provider: str
    model: str
    stage: SummaryPass
    call_index: int
    request_character_count: int
    item_ids: tuple[str, ...]
    response_id: str | None = None
    request_id: str | None = None
```

In `summarize.py`, replace message-only errors:

```python
class SummaryValidationError(RuntimeError):
    def __init__(
        self,
        code: str,
        field: str,
        context: SummaryFailureContext | None = None,
        response_shape: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.field = field
        self.context = context
        self.response_shape = response_shape
        super().__init__(f"{code} at {field}")
```

The `response_shape` field is populated later by the diagnostics projector and
must never hold the original payload.

- [x] **Step 5: Give every validator branch a stable code and path**

Split `_ids` and `_evidence` checks so empty, duplicate, and unknown cases have
distinct codes. Keep exception text derived only from static code/path strings.
Use `invalid-episode-allocation` for incomplete, duplicate, or extra final
allocation; the support shape will carry content-free counts.

- [x] **Step 6: Enrich errors at provider boundaries**

Wrap each `validate_digest`, `validate_merge`, and
`validate_final_allocation` call. Re-raise a new error with the original
code/path plus a `SummaryFailureContext` constructed from the request and
`ProviderResponse`. Chunk calls are one-based in chronological order; the merge
call index follows all chunk calls.

- [x] **Step 7: Verify diagnostics and all existing behavior**

Run:

```bash
uv run pytest tests/test_summarize.py tests/test_cli.py -v
uv run pytest -q
```

Expected: each invalid fixture has a stable content-free code/path and all valid
digests are unchanged.

- [x] **Step 8: Commit typed validation failures**

```bash
git add src/daytrace/models.py src/daytrace/summarize.py tests/test_summarize.py tests/test_cli.py
git commit -m "feat: expose safe AI validation diagnostics"
```

---

### Task 5: Redacted Support Artifact and CLI Integration

**Files:**
- Create: `src/daytrace/summary_diagnostics.py`
- Modify: `src/daytrace/summarize.py`
- Modify: `src/daytrace/cli.py`
- Create: `tests/test_summary_diagnostics.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: a `SummaryValidationError` and its untrusted response payload only at the validation boundary.
- Produces: `safe_response_shape(payload, allowed_ids) -> Mapping[str, object]`, `render_summary_failure_json(exc, provider, model) -> str`, and CLI option `--debug-output PATH`.

- [x] **Step 1: Add failing safe-shape tests**

Use an invalid synthetic payload containing private generated labels/text and an
unknown credential-shaped ID. Assert the projection contains only:

- known supplied IDs;
- workstream/topic/outcome collection sizes;
- duplicate and unknown counts;
- no label, topic text, outcome text, unknown ID value, or secret fragment.

```python
shape = safe_response_shape(payload, {"episode-001", "episode-002"})
rendered = json.dumps(shape)
assert shape["workstream_count"] == 1
assert shape["known_allocated_ids"] == ["episode-001"]
assert shape["unknown_id_count"] == 1
assert "private generated text" not in rendered
assert "credential-shaped-unknown-id" not in rendered
```

- [x] **Step 2: Add failing support JSON tests**

Construct a `SummaryValidationError` with context and safe shape. Require this
exact top-level contract:

```json
{
  "schema": "daytrace.ai-failure.v1",
  "daytrace_version": "0.3.2",
  "provider": "openai",
  "model": "user-model",
  "stage": "chunk",
  "call_index": 1,
  "request_character_count": 1234,
  "item_count": 2,
  "item_ids": ["episode-001", "episode-002"],
  "response_id": "resp_test",
  "request_id": "req_test",
  "validation": {"code": "unknown-ids", "field": "workstreams[0].episode_ids"},
  "response_shape": {}
}
```

Omit optional ID/context keys when unavailable rather than serializing private
exception representations.

- [x] **Step 3: Add failing CLI tests**

Cover:

- `--debug-output` requires `--summary ai`;
- debug and primary output paths must differ;
- a validation failure writes both deterministic fallback and valid support JSON;
- stderr includes only static `code=`, `field=`, `stage=`, call, and safe opaque IDs;
- stderr includes the DayTrace version and a content-free notice that a local
  support artifact will be written when `--debug-output` is selected;
- generated text, ActivityWatch titles, and API key are absent from stderr and support JSON;
- an atomic debug write failure reports a content-free output error and returns 1 after preserving any existing debug file.

- [x] **Step 4: Run focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_summary_diagnostics.py tests/test_cli.py -v
```

Expected: module, renderer, parser option, and contextual warning are missing.

- [x] **Step 5: Implement safe response-shape projection**

`safe_response_shape` must tolerate arbitrary Python objects and never call
`repr` or `str` on untrusted values. Inspect only recognized mapping keys and
list lengths. For each recognized ID list, retain values only when they are
exact string members of `allowed_ids`; report unknown and duplicate counts as
integers. Do not retain workstream labels or any `text` field.

At the `summarize_bundle` validation boundary, compute this projection from the
response payload and attach only the projection—not the payload—to the re-raised
`SummaryValidationError`.

- [x] **Step 6: Implement versioned support rendering**

`render_summary_failure_json` builds a fresh allow-listed dictionary and uses
`json.dumps(..., ensure_ascii=False, sort_keys=True, indent=2) + "\n"`. It never
serializes exception `__dict__` or arbitrary exception arguments.

Pass provider, model, and response/request identifiers through one
safe-identifier helper. Values outside `^[A-Za-z0-9._:-]{1,200}$` become fixed
redacted labels; they are never copied verbatim into stderr or JSON.

- [x] **Step 7: Add CLI option and safe warning detail**

Add:

```python
activitywatch.add_argument(
    "--debug-output",
    type=Path,
    help="write privacy-safe AI failure metadata as JSON",
)
```

Validate it only with AI mode and ensure it differs from `--output`. On caught
`SummaryValidationError`, append safe fields to the existing fallback warning.
If `--debug-output` is set, render and atomically write the support JSON with the
existing `_write_atomic` helper.

Before confirmation, print the static sentence `AI failure metadata will be
written locally if this run fails.` when debug output is enabled. Do not print
the path because it may contain a username. Include `daytrace <version>` in the
content-free failure warning.

Provider and privacy failures may write a smaller artifact containing provider,
model, failure kind/code, and any safe request metadata available; they must not
invent response metadata.

- [x] **Step 8: Verify CLI and full suite**

Run:

```bash
uv run pytest tests/test_summary_diagnostics.py tests/test_cli.py -v
uv run pytest -q
```

Expected: fallback remains unchanged, debug JSON is opt-in and private, and all
tests pass.

- [x] **Step 9: Commit support diagnostics**

```bash
git add src/daytrace/summary_diagnostics.py src/daytrace/summarize.py src/daytrace/cli.py tests/test_summary_diagnostics.py tests/test_cli.py
git commit -m "feat: write redacted AI failure reports"
```

---

### Task 6: Documentation, Version, and Release Verification

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/daytrace/__init__.py`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: completed 0.3.2 behavior and public CLI.
- Produces: published DayTrace 0.3.2 wheel/source archive, tag `v0.3.2`, and user command for the sanitized raw recapture.

- [x] **Step 1: Update README privacy and troubleshooting guidance**

Document:

```powershell
uvx --refresh --link-mode=copy daytrace@0.3.2 activitywatch `
  --date 2026-09-10 `
  --summary ai `
  --provider openai `
  --model gpt-5.6-terra `
  --debug-output daytrace-ai-failure.json `
  --output daytrace.md
```

Explain that OpenAI calls use `store=False`, the debug artifact contains only
allow-listed structural metadata, validation failures still produce the
deterministic fallback, and users must never attach or paste their API key.

Add the post-release recapture command:

```powershell
uvx --refresh --link-mode=copy daytrace@0.3.2 activitywatch `
  --date 2026-09-10 `
  --format json `
  --raw `
  --output daytrace-raw.json
```

State that raw output is sanitized but still personally sensitive and must be
reviewed before sharing.

- [x] **Step 2: Bump all package metadata to 0.3.2**

Set:

```toml
# pyproject.toml
version = "0.3.2"
```

```python
# src/daytrace/__init__.py
__version__ = "0.3.2"
```

Run `uv lock` and verify no dependency change beyond the root package version.

- [x] **Step 3: Run release verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv build --no-sources
python -m zipfile -l dist/daytrace-0.3.2-py3-none-any.whl
tar -tf dist/daytrace-0.3.2.tar.gz
git diff --check
git status --short
```

If `ruff` or `mypy` are not configured project dependencies, record that fact
and rely on the repository's configured pytest/build/CI gates rather than adding
new tooling in a patch release. Expected: 0 failures; both archives contain the
package, metadata, license, and no personal trace/support artifact.

- [x] **Step 4: Commit release metadata**

```bash
git add README.md pyproject.toml src/daytrace/__init__.py uv.lock
git commit -m "release: prepare 0.3.2"
```

- [ ] **Step 5: Perform pre-publication review and verification gates**

Use `superpowers:requesting-code-review` and address all correctness, privacy,
and compatibility findings. Then use `superpowers:verification-before-completion`
and repeat the full test/build/archive checks from a clean tree.

- [ ] **Step 6: Push `main` and verify CI**

```bash
git push origin main
gh run list --branch main --limit 1
gh run watch <run-id> --exit-status
```

Expected: remote `main` points to the release commit and the Linux/macOS/Windows
matrix succeeds.

- [ ] **Step 7: Publish wheel and source archive to PyPI**

Use the repository's established token source without printing it:

```bash
uv publish dist/daytrace-0.3.2-py3-none-any.whl dist/daytrace-0.3.2.tar.gz
```

Expected: PyPI accepts both artifacts. Never place the token in shell history,
command output, source files, or Git configuration.

- [ ] **Step 8: Tag and verify the public package**

```bash
git tag -a v0.3.2 -m "DayTrace 0.3.2"
git push origin v0.3.2
uvx --refresh --link-mode=copy daytrace@0.3.2 --help
git status --short --branch
```

Expected: the tag points to the release commit, the public wheel exposes the
CLI, and the local tree is clean and synchronized with `origin/main`.

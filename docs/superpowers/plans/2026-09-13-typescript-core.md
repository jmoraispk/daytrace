# Browser-Compatible TypeScript Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship synchronized Python and npm `daytrace` 0.4.0 packages, with a browser-compatible TypeScript core that matches the Python pipeline and is directly consumable by the Second Brain plugin.

**Architecture:** Add a standalone, dependency-free-at-runtime ESM package under `packages/daytrace-core/`. Mirror the Python modules, inject ActivityWatch HTTP and AI provider boundaries, and enforce parity with synthetic fixtures produced and checked by the Python reference implementation.

**Tech Stack:** Python 3.11+, uv, pytest, Node 24, npm, TypeScript 7.0.2, Vitest 5.0.0, esbuild 0.28.2, and browser-standard `Intl`, `URL`, `AbortSignal`, and `performance` APIs.

**Spec:** `docs/superpowers/specs/2026-09-13-typescript-core-design.md`

## Global Constraints

- Keep the existing Python implementation and CLI intact.
- Publish both Python and npm packages as version `0.4.0`.
- Public npm package name: `@jmoraispk/daytrace`; source directory: `packages/daytrace-core/`.
- Export only ESM JavaScript and TypeScript declarations.
- The shipped TypeScript package has zero runtime dependencies and imports no Node built-ins.
- Use injected interfaces for ActivityWatch HTTP and AI providers.
- Support `AbortSignal` cancellation and content-free progress callbacks.
- Preserve existing schema strings and semantics.
- Commit only synthetic cross-language fixtures; never commit personal ActivityWatch data.
- Work and commit directly on `main`, as requested.
- Publish PyPI and npm packages only after all release checks pass; publication is authorized.

---

## Planned File Structure

### Package and tooling

- Create `packages/daytrace-core/package.json` — npm metadata, exports, and scripts.
- Create `packages/daytrace-core/package-lock.json` — locked development tools.
- Create `packages/daytrace-core/tsconfig.json` — strict browser-compatible compilation.
- Create `packages/daytrace-core/vitest.config.ts` — test configuration.
- Create `packages/daytrace-core/LICENSE` — packaged MIT license.
- Create `packages/daytrace-core/README.md` — npm-facing API and integration guide.
- Create `packages/daytrace-core/scripts/browser-smoke.mjs` — pack/import/esbuild verification.

### TypeScript source

- Create `packages/daytrace-core/src/models.ts` — readonly domain types, errors, injected interfaces.
- Create `packages/daytrace-core/src/time.ts` — ISO timestamp and IANA day-window arithmetic.
- Create `packages/daytrace-core/src/diagnostics.ts` — aggregate diagnostic collector.
- Create `packages/daytrace-core/src/source.ts` — server validation and ActivityWatch transport adapter.
- Create `packages/daytrace-core/src/normalize.ts` — raw event conversion and clipping.
- Create `packages/daytrace-core/src/transform.ts` — AFK subtraction.
- Create `packages/daytrace-core/src/sanitize.ts` — text, URL, path, email, and secret sanitation.
- Create `packages/daytrace-core/src/fusion.ts` — overlapping-source fusion.
- Create `packages/daytrace-core/src/sessionize.ts` — session construction and signals.
- Create `packages/daytrace-core/src/episode.ts` — episode compaction and invariants.
- Create `packages/daytrace-core/src/cloud-privacy.ts` — cloud minimization and final egress checks.
- Create `packages/daytrace-core/src/prompts.ts` — exact Python prompt text.
- Create `packages/daytrace-core/src/summarize.ts` — planning, validation, merge, provider orchestration, fallback.
- Create `packages/daytrace-core/src/summary-diagnostics.ts` — content-free failure artifacts.
- Create `packages/daytrace-core/src/json-output.ts` — deterministic JSON renderers.
- Create `packages/daytrace-core/src/markdown.ts` — deterministic and AI Markdown renderers.
- Create `packages/daytrace-core/src/report.ts` — deterministic report aggregation.
- Create `packages/daytrace-core/src/activitywatch.ts` — `collectDay` orchestration and progress.
- Create `packages/daytrace-core/src/index.ts` — supported public API.

### Tests, fixtures, docs, and CI

- Create `packages/daytrace-core/test/*.test.ts` — focused TypeScript unit and integration tests.
- Create `tests/fixtures/cross-language/*.json` and `*.md` — synthetic parity fixtures.
- Create `tests/parity_adapter.py` — Python-reference fixture construction and serialization.
- Create `tests/test_typescript_parity.py` — fixture freshness checks against Python.
- Modify `.github/workflows/ci.yml` — Node/package/browser job.
- Rewrite `README.md` — polished Python/TypeScript product documentation.
- Modify `pyproject.toml`, `src/daytrace/__init__.py`, and `uv.lock` — Python 0.4.0.

---

### Task 1: Package Scaffold, Models, Time, and Diagnostics

**Files:**
- Create: `packages/daytrace-core/package.json`
- Create: `packages/daytrace-core/package-lock.json`
- Create: `packages/daytrace-core/tsconfig.json`
- Create: `packages/daytrace-core/vitest.config.ts`
- Create: `packages/daytrace-core/LICENSE`
- Create: `packages/daytrace-core/src/models.ts`
- Create: `packages/daytrace-core/src/time.ts`
- Create: `packages/daytrace-core/src/diagnostics.ts`
- Create: `packages/daytrace-core/src/index.ts`
- Test: `packages/daytrace-core/test/time.test.ts`
- Test: `packages/daytrace-core/test/diagnostics.test.ts`

**Interfaces:**
- Produces: `IsoDate`, `IsoTimestamp`, all domain interfaces, `SourceKind`, `DiagnosticCode`, `ProgressEvent`, `ProgressCallback`, `SummaryProvider`, `ActivityWatchTransport`, typed content-free errors, `resolveDay(date, timezoneName)`, `DiagnosticCollector`, and `DAYTRACE_VERSION = "0.4.0"`.
- Consumes: browser-standard `Intl`, `URL`, `AbortSignal`, and `performance`; no application state.

- [ ] **Step 1: Write failing foundation tests**

```ts
it("resolves DST day windows", () => {
  expect(resolveDay("2026-03-08", "America/Los_Angeles")).toEqual({
    timezoneName: "America/Los_Angeles",
    start: "2026-03-08T08:00:00.000Z",
    end: "2026-03-09T07:00:00.000Z",
  });
  expect(resolveDay("2026-11-01", "America/Los_Angeles")).toEqual({
    timezoneName: "America/Los_Angeles",
    start: "2026-11-01T07:00:00.000Z",
    end: "2026-11-02T08:00:00.000Z",
  });
});

it("aggregates diagnostics in stable code order", () => {
  const collector = new DiagnosticCollector();
  collector.add("sanitized-field", 2);
  collector.add("non-positive-event");
  expect(collector.snapshot()).toEqual([
    { code: "non-positive-event", count: 1 },
    { code: "sanitized-field", count: 2 },
  ]);
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/time.test.ts test/diagnostics.test.ts`  
Expected: FAIL because the package and modules do not exist.

- [ ] **Step 3: Add package metadata and strict compiler settings**

Use `type: "module"`, `sideEffects: false`, an export map pointing to
`dist/index.js` and `dist/index.d.ts`, `files: ["dist", "README.md", "LICENSE"]`,
and scripts for `test`, `typecheck`, `build`, `pack:check`, and `smoke:browser`.
Set TypeScript libraries to `ES2022` and `DOM`, `moduleResolution` to `Bundler`,
and enable `strict`, `noUncheckedIndexedAccess`, and declaration output.

- [ ] **Step 4: Implement the model, time, and diagnostic foundations**

```ts
export interface DayWindow {
  readonly timezoneName: string;
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
}

export interface ProgressEvent {
  readonly stage: ProgressStage;
  readonly current?: number;
  readonly total?: number;
  readonly elapsedSeconds: number;
}

export function resolveDay(day: IsoDate, timezoneName: string): DayWindow;
```

Reject invalid dates and unavailable IANA zones with `DaytraceInputError`
containing only a fixed code and message. Use `Intl.DateTimeFormat` to resolve
local midnight to UTC and verify the resulting local calendar fields.

- [ ] **Step 5: Run foundation verification**

Run: `npm --prefix packages/daytrace-core test -- --run test/time.test.ts test/diagnostics.test.ts`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core
git commit -m "feat: scaffold TypeScript daytrace core"
```

### Task 2: ActivityWatch Source, Normalization, AFK Removal, and Sanitization

**Files:**
- Create: `packages/daytrace-core/src/source.ts`
- Create: `packages/daytrace-core/src/normalize.ts`
- Create: `packages/daytrace-core/src/transform.ts`
- Create: `packages/daytrace-core/src/sanitize.ts`
- Test: `packages/daytrace-core/test/source.test.ts`
- Test: `packages/daytrace-core/test/normalize.test.ts`
- Test: `packages/daytrace-core/test/transform.test.ts`
- Test: `packages/daytrace-core/test/sanitize.test.ts`

**Interfaces:**
- Consumes: model types and `DayWindow` from Task 1.
- Produces: `parseServerUrl`, `ActivityWatchSource`, `normalizeEvents`, `removeAfk`, `sanitizeRecords`, `sanitizeGeneratedText`, and `containsSecret`.

- [ ] **Step 1: Write failing transport and deterministic-stage tests**

```ts
it("clips events to the selected UTC day window", () => {
  const result = normalizeEvents(bucket, [crossingEvent], window, diagnose);
  expect(result[0]?.start).toBe(window.start);
  expect(result[0]?.durationSeconds).toBe(30);
});

it("subtracts AFK time without discarding context records", () => {
  expect(removeAfk([windowRecord, afkRecord, editorRecord])).toEqual([
    expectedWindowBeforeAfk,
    expectedWindowAfterAfk,
    editorRecord,
  ]);
});

it("redacts secrets and keeps only safe repository URL paths", () => {
  const result = sanitizeRecords(records, diagnose);
  expect(result[0]?.title).toBe("Deploy [redacted-secret]");
  expect(result[0]?.urlPath).toBe("/jmoraispk/daytrace");
});
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/source.test.ts test/normalize.test.ts test/transform.test.ts test/sanitize.test.ts`  
Expected: FAIL on missing modules.

- [ ] **Step 3: Implement source validation and injected HTTP conversion**

```ts
export interface ActivityWatchRequest {
  readonly server: string;
  readonly path: string;
  readonly query?: Readonly<Record<string, string>>;
  readonly signal?: AbortSignal;
}

export interface ActivityWatchTransport {
  request(input: ActivityWatchRequest): Promise<unknown>;
}
```

Accept only root `http`/`https` server URLs without credentials, query, or
fragment. Convert `/api/0/info`, `/api/0/buckets`, and encoded bucket-event
responses into validated `RawBucket` and `RawEvent` values. Wrap transport and
shape failures in fixed, content-free error messages.

- [ ] **Step 4: Port normalization, AFK subtraction, and sanitizer semantics**

Port Python constants and ordering exactly: supported bucket mapping, half-open
clipping, non-positive diagnostics, union/subtraction of AFK intervals, NFKC and
whitespace normalization, email/secret replacement, safe GitHub/GitLab paths,
auth-path removal, file basenames, 500-character limits, and stable evidence IDs.

- [ ] **Step 5: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/source.test.ts test/normalize.test.ts test/transform.test.ts test/sanitize.test.ts`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: port ActivityWatch normalization and privacy"
```

### Task 3: Fusion, Sessionization, and Episode Compaction

**Files:**
- Create: `packages/daytrace-core/src/fusion.ts`
- Create: `packages/daytrace-core/src/sessionize.ts`
- Create: `packages/daytrace-core/src/episode.ts`
- Test: `packages/daytrace-core/test/fusion.test.ts`
- Test: `packages/daytrace-core/test/sessionize.test.ts`
- Test: `packages/daytrace-core/test/episode.test.ts`

**Interfaces:**
- Consumes: sanitized observations, diagnostics, ISO time utilities.
- Produces: `fuseObservations`, `sessionize`, `compactSessions`, `EpisodeInvariantError`.

- [ ] **Step 1: Write failing overlap, session, and duration-conservation tests**

```ts
it("uses current-window time as authority and browser as context", () => {
  const slices = fuseObservations([windowObservation, browserObservation], diagnose);
  expect(slices).toEqual([expectedEnrichedSlice]);
});

it("splits sessions on the Python gap threshold", () => {
  const bundle = sessionize("2026-09-10", window, separatedSlices, []);
  expect(bundle.sessions.map((item) => item.sessionId)).toEqual([
    "session-001",
    "session-002",
  ]);
});

it("conserves active duration while compacting sessions", () => {
  const result = compactSessions(sessionBundle);
  expect(sum(result.episodes.map((item) => item.activeSeconds))).toBe(
    sum(sessionBundle.sessions.map((item) => item.activeSeconds)),
  );
});
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/fusion.test.ts test/sessionize.test.ts test/episode.test.ts`  
Expected: FAIL on missing pipeline modules.

- [ ] **Step 3: Port fusion and sessionization**

Preserve source precedence, boundary generation, conflict diagnostics, context
deduplication, focus accounting, label selection, session-gap rules, signal
generation, stable ordering, and `session-NNN` identifiers.

- [ ] **Step 4: Port episode compatibility and compaction**

Preserve anchor selection, compatible-session grouping, application/activity
label counts, outcome signal deduplication, `episode-NNN` identifiers, and the
absolute/relative tolerance used by Python's duration conservation invariant.

- [ ] **Step 5: Verify GREEN and the full TypeScript suite**

Run: `npm --prefix packages/daytrace-core test`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: port sessions and episode compaction"
```

### Task 4: ActivityWatch Collection and Content-Free Progress

**Files:**
- Create: `packages/daytrace-core/src/activitywatch.ts`
- Modify: `packages/daytrace-core/src/index.ts`
- Test: `packages/daytrace-core/test/activitywatch.test.ts`
- Test: `packages/daytrace-core/test/progress.test.ts`

**Interfaces:**
- Consumes: transport and deterministic stages from Tasks 1–3.
- Produces: `collectDay(options): Promise<EpisodeBundle>`, `CollectDayOptions`, and fixed progress stages.

- [ ] **Step 1: Write a failing end-to-end synthetic collection test**

```ts
const bundle = await collectDay({
  day: "2026-09-10",
  timezoneName: "UTC",
  server: "http://127.0.0.1:5600",
  transport: syntheticTransport,
  onProgress: (event) => progress.push(event),
});
expect(bundle.episodes).toEqual(expectedEpisodes);
expect(progress.map((item) => item.stage)).toEqual([
  "activitywatch:info",
  "activitywatch:buckets",
  "activitywatch:events",
  "pipeline:normalize",
  "pipeline:sanitize",
  "pipeline:fuse",
  "pipeline:sessions",
  "pipeline:episodes",
  "complete",
]);
expect(JSON.stringify(progress)).not.toContain("Synthetic Secret Project");
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/activitywatch.test.ts test/progress.test.ts`  
Expected: FAIL because `collectDay` is missing.

- [ ] **Step 3: Implement collection orchestration and cancellation**

Check `AbortSignal` before/after each transport call and between pipeline stages.
Do not catch or convert aborts. Emit progress from a monotonic browser clock with
integer elapsed seconds, fixed stages, and count/index fields only.

- [ ] **Step 4: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/activitywatch.test.ts test/progress.test.ts`  
Expected: PASS, including cancellation before the next transport request.

- [ ] **Step 5: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: add browser-safe ActivityWatch collection"
```

### Task 5: Deterministic Reports, JSON, and Markdown

**Files:**
- Create: `packages/daytrace-core/src/report.ts`
- Create: `packages/daytrace-core/src/json-output.ts`
- Create: `packages/daytrace-core/src/markdown.ts`
- Modify: `packages/daytrace-core/src/index.ts`
- Test: `packages/daytrace-core/test/report.test.ts`
- Test: `packages/daytrace-core/test/json-output.test.ts`
- Test: `packages/daytrace-core/test/markdown.test.ts`

**Interfaces:**
- Consumes: episode/session bundles.
- Produces: `buildReport`, `renderEpisodeJson`, `renderEpisodeMarkdown`, and deterministic formatting helpers used by AI rendering.

- [ ] **Step 1: Write failing literal-output tests**

```ts
expect(renderEpisodeJson(bundle)).toBe(expectedEpisodeJsonWithFinalNewline);
expect(renderEpisodeMarkdown(bundle)).toBe(expectedEpisodeMarkdown);
expect(buildReport(bundle).activeSeconds).toBe(3720.5);
```

Assertions use hand-checked literal fixtures, not values generated by the
TypeScript implementation.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/report.test.ts test/json-output.test.ts test/markdown.test.ts`  
Expected: FAIL on missing renderers.

- [ ] **Step 3: Port report aggregation and JSON schemas**

Preserve schema names, snake_case serialized fields, stable key order, UTC/local
timestamp formatting, application totals, focused duration, diagnostics, raw
session detail switches, indentation, Unicode handling, and final newline.

- [ ] **Step 4: Port deterministic Markdown**

Preserve headings, time ranges, duration formatting including `<1m`, escaping,
application/activity lists, episode evidence/detail sections, empty-day output,
and trailing newline behavior.

- [ ] **Step 5: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/report.test.ts test/json-output.test.ts test/markdown.test.ts`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: add deterministic TypeScript renderers"
```

### Task 6: Cloud Privacy, Prompts, and Summary Planning

**Files:**
- Create: `packages/daytrace-core/src/cloud-privacy.ts`
- Create: `packages/daytrace-core/src/prompts.ts`
- Create: `packages/daytrace-core/src/summarize.ts`
- Modify: `packages/daytrace-core/src/index.ts`
- Test: `packages/daytrace-core/test/cloud-privacy.test.ts`
- Test: `packages/daytrace-core/test/summarize-plan.test.ts`
- Test: `packages/daytrace-core/test/prompts.test.ts`

**Interfaces:**
- Consumes: episode bundles, sanitizer, model types.
- Produces: `assertCloudSafePayload`, minimizers, exact prompts, strict response formats, `buildSummaryPlan`, and `buildMergeRequest`.

- [ ] **Step 1: Write failing minimization and chunk-plan tests**

```ts
expect(minimizeCloudTitle("Slack", "Alex (DM) - Slack")).toBe(
  "Direct message - Slack",
);
expect(() => assertCloudSafePayload({ title: "token=abcdefghijkl" })).toThrow(
  CloudPrivacyError,
);
expect(buildSummaryPlan(largeBundle).requests.map((item) => item.episodeIds)).toEqual(
  expectedChunkEpisodeIds,
);
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/cloud-privacy.test.ts test/summarize-plan.test.ts test/prompts.test.ts`  
Expected: FAIL on missing modules/functions.

- [ ] **Step 3: Port cloud minimization and exact prompts**

Copy both Python prompts byte-for-byte. Preserve direct-message, meeting,
email/calendar, filename, and 500-character minimization rules. Recursively
reject any payload whose strings change under generated-text sanitation.

- [ ] **Step 4: Port summary planning**

Preserve `PROMPT_SCHEMA`, request schema, minimized episode payload shape,
included data categories, character counting using compact sorted-key JSON,
maximum request characters, episode-boundary chunking, empty-bundle behavior,
provisional workstream IDs, merge payload, and strict response JSON schemas.

- [ ] **Step 5: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/cloud-privacy.test.ts test/summarize-plan.test.ts test/prompts.test.ts`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: port AI summary planning"
```

### Task 7: Structured Response, Evidence, and Merge Validation

**Files:**
- Modify: `packages/daytrace-core/src/summarize.ts`
- Test: `packages/daytrace-core/test/summarize-validation.test.ts`

**Interfaces:**
- Consumes: raw `unknown` provider payloads and allowed ID sets.
- Produces: `validateDigest`, `validateMerge`, `assembleMergedDigest`, `validateFinalAllocation`, and `SummaryValidationError`.

- [ ] **Step 1: Write failing table-driven validator tests**

```ts
it.each([
  [wrongSchema, "invalid-schema", "schema"],
  [unknownEvidence, "unknown-id", "workstreams[0].topics[0].evidence"],
  [duplicateAllocation, "invalid-episode-allocation", "episode-allocation"],
])("rejects malformed digest payloads", (payload, code, field) => {
  expectValidationFailure(() => validateDigest(payload, allowed), code, field);
});
```

Add corresponding valid digest, generated-secret, merge duplicate, bounds,
enum, missing/extra key, and final-allocation tests.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/summarize-validation.test.ts`  
Expected: FAIL because validation is incomplete.

- [ ] **Step 3: Port strict validators and merged assembly**

Reject booleans where integers are expected, non-plain objects, extra/missing
keys, oversized arrays/text, unknown/duplicate IDs, empty required evidence,
invalid enums, unsafe generated prose, and incomplete global allocation.
Preserve workstream order and Python's local handling of unmerged singletons.

- [ ] **Step 4: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/summarize-validation.test.ts`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/daytrace-core/src/summarize.ts packages/daytrace-core/test/summarize-validation.test.ts
git commit -m "feat: validate TypeScript AI summaries"
```

### Task 8: AI Provider Orchestration, Repair, Fallback, and Progress

**Files:**
- Modify: `packages/daytrace-core/src/models.ts`
- Modify: `packages/daytrace-core/src/summarize.ts`
- Modify: `packages/daytrace-core/src/index.ts`
- Test: `packages/daytrace-core/test/summarize-provider.test.ts`
- Test: `packages/daytrace-core/test/summary-progress.test.ts`

**Interfaces:**
- Consumes: summary plan and validation functions.
- Produces: `summarizeBundle`, `summarizeBundleOrFallback`, `SummaryProvider`, `SummaryOutcome`, and content-free contextual failures.

- [ ] **Step 1: Write failing single-chunk, repair, merge, fallback, and abort tests**

```ts
const { digest, provenance } = await summarizeBundle(bundle, provider, plan);
expect(digest).toEqual(validDigest);
expect(provenance.requestCount).toBe(1);

expect(provider.calls.map((call) => call.passKind)).toEqual([
  "chunk",
  "chunk",
  "merge",
]);

const outcome = await summarizeBundleOrFallback(bundle, failingProvider);
expect(outcome.kind).toBe("deterministic");
expect(JSON.stringify(outcome)).not.toContain("private provider message");
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/summarize-provider.test.ts test/summary-progress.test.ts`  
Expected: FAIL because orchestration is missing.

- [ ] **Step 3: Implement the injected provider contract**

```ts
export interface SummaryProvider {
  complete(
    request: ProviderRequest,
    options?: ProviderCallOptions,
  ): Promise<ProviderResponse>;
}

export interface ProviderRequest {
  readonly passKind: "chunk" | "merge";
  readonly payload: Readonly<Record<string, unknown>>;
  readonly instructions: string;
  readonly responseFormat: Readonly<Record<string, unknown>>;
}
```

Run `assertCloudSafePayload` immediately before `complete`. Wrap arbitrary
provider exceptions without retaining their messages or values.

- [ ] **Step 4: Port orchestration and deterministic fallback**

Preserve one repair attempt only for allocation failure, character-limit guard,
chunk order, optional merge, token aggregation, safe response/request IDs,
contextual validation metadata, and final allocation. Emit fixed progress events
for call start, response, validation, repair, merge, and completion. Abort errors
must bypass fallback unchanged.

- [ ] **Step 5: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/summarize-provider.test.ts test/summary-progress.test.ts`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: orchestrate TypeScript AI summaries"
```

### Task 9: AI Renderers and Failure Diagnostics

**Files:**
- Create: `packages/daytrace-core/src/summary-diagnostics.ts`
- Modify: `packages/daytrace-core/src/json-output.ts`
- Modify: `packages/daytrace-core/src/markdown.ts`
- Modify: `packages/daytrace-core/src/index.ts`
- Test: `packages/daytrace-core/test/ai-output.test.ts`
- Test: `packages/daytrace-core/test/summary-diagnostics.test.ts`

**Interfaces:**
- Consumes: bundles, validated digests, provenance, and safe failure context.
- Produces: `renderDigestJson`, `renderDigestMarkdown`, `safeResponseShape`, and `renderSummaryFailureJson`.

- [ ] **Step 1: Write failing AI table and failure-artifact tests**

```ts
expect(renderDigestMarkdown(bundle, digest, provenance)).toBe(
  expectedJournalTable,
);
expect(JSON.parse(renderSummaryFailureJson(failure))).toEqual({
  schema: "daytrace.ai-failure.v1",
  daytrace_version: "0.4.0",
  provider: "openai",
  model: "gpt-test",
  validation: { code: "invalid-schema", field: "schema" },
  response_shape: expectedSafeShape,
});
```

- [ ] **Step 2: Verify RED**

Run: `npm --prefix packages/daytrace-core test -- --run test/ai-output.test.ts test/summary-diagnostics.test.ts`  
Expected: FAIL on missing AI renderers.

- [ ] **Step 3: Port AI JSON and Markdown rendering**

Preserve `daytrace.workstream-report.v2`, journal table headings, confidence and
achievement wording, topic/outcome evidence handling, primary-allocation
durations, optional details, provenance, escaping, and deterministic ordering.

- [ ] **Step 4: Port allow-listed failure diagnostics**

Preserve safe identifier/code/field regular expressions, count/list allow lists,
response-shape extraction, duplicate/unknown counts, indentation, key order, and
final newline. Never serialize model prose or raw request/response content.

- [ ] **Step 5: Verify GREEN**

Run: `npm --prefix packages/daytrace-core test -- --run test/ai-output.test.ts test/summary-diagnostics.test.ts`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/daytrace-core/src packages/daytrace-core/test
git commit -m "feat: render TypeScript workstream reports"
```

### Task 10: Synthetic Cross-Language Parity Fixtures and Gates

**Files:**
- Create: `tests/parity_adapter.py`
- Create: `tests/test_typescript_parity.py`
- Create: `tests/fixtures/cross-language/pipeline-input.json`
- Create: `tests/fixtures/cross-language/pipeline-expected.json`
- Create: `tests/fixtures/cross-language/episode-expected.md`
- Create: `tests/fixtures/cross-language/digest-input.json`
- Create: `tests/fixtures/cross-language/digest-expected.json`
- Create: `tests/fixtures/cross-language/digest-expected.md`
- Create: `tests/fixtures/cross-language/dst-expected.json`
- Create: `packages/daytrace-core/test/parity.test.ts`

**Interfaces:**
- Consumes: all deterministic and AI core functions from Tasks 1–9.
- Produces: committed, synthetic parity contracts checked by both languages.

- [ ] **Step 1: Write the failing Python fixture-freshness test**

```py
def test_cross_language_fixture_matches_python_reference() -> None:
    expected = json.loads(EXPECTED.read_text())
    assert build_python_reference_fixture() == expected
```

- [ ] **Step 2: Verify Python RED**

Run: `uv run pytest tests/test_typescript_parity.py -v`  
Expected: FAIL because fixtures and adapter are absent.

- [ ] **Step 3: Add invented raw/provider inputs and Python reference adapter**

Use only fictional values such as `Example Editor`, `example.test`,
`octo/demo-project`, and obviously fake secret strings. Exercise overlap, AFK,
sanitization, outcome signals, compaction, diagnostics, DST windows, summary
planning/validation/merge, deterministic output, AI output, and failures.

- [ ] **Step 4: Generate and review committed expected artifacts**

Run: `uv run python tests/parity_adapter.py --write`  
Expected: writes stable JSON/Markdown fixture outputs. Review with
`git diff -- tests/fixtures/cross-language` and confirm no usernames, home paths,
real domains, keys, or personal titles occur.

- [ ] **Step 5: Verify Python GREEN**

Run: `uv run pytest tests/test_typescript_parity.py -v`  
Expected: PASS.

- [ ] **Step 6: Write the failing TypeScript parity test, then close differences**

```ts
it("matches the Python reference fixture", async () => {
  const actual = await runTypeScriptReferenceFixture(input);
  expect(actual).toEqual(expected);
  expect(renderEpisodeMarkdown(actual.bundle)).toBe(expectedEpisodeMarkdown);
  expect(renderDigestMarkdown(actual.bundle, digest, provenance)).toBe(
    expectedDigestMarkdown,
  );
});
```

Run before fixes: `npm --prefix packages/daytrace-core test -- --run test/parity.test.ts`  
Expected: FAIL on any semantic drift. Adjust TypeScript production behavior,
not expected fixtures, until the reference output matches.

- [ ] **Step 7: Run all parity and unit tests**

Run: `uv run pytest && npm --prefix packages/daytrace-core test`  
Expected: both suites PASS.

- [ ] **Step 8: Commit**

```bash
git add tests packages/daytrace-core/test packages/daytrace-core/src
git commit -m "test: enforce Python TypeScript parity"
```

### Task 11: Package Build and Browser Bundle Smoke Test

**Files:**
- Modify: `packages/daytrace-core/package.json`
- Modify: `packages/daytrace-core/tsconfig.json`
- Create: `packages/daytrace-core/scripts/browser-smoke.mjs`
- Modify: `packages/daytrace-core/src/index.ts`
- Test: packed artifact and generated browser bundle.

**Interfaces:**
- Consumes: complete public TypeScript API.
- Produces: `dist/index.js`, `dist/index.d.ts`, and `daytrace-0.4.0.tgz`.

- [ ] **Step 1: Write the smoke script before finalizing packaging**

The script creates a temporary consumer, installs the tarball, writes:

```ts
import { DAYTRACE_VERSION, buildSummaryPlan, renderEpisodeJson } from "@jmoraispk/daytrace";
globalThis.__daytraceSmoke = {
  version: DAYTRACE_VERSION,
  buildSummaryPlan,
  renderEpisodeJson,
};
```

and invokes esbuild with `bundle: true`, `platform: "browser"`,
`format: "esm"`, and no fallback/polyfill plugins.

- [ ] **Step 2: Run smoke and verify RED**

Run: `npm --prefix packages/daytrace-core run smoke:browser`  
Expected: FAIL before the build/pack scripts and complete export map exist.

- [ ] **Step 3: Finalize build, export map, and pack contents**

Compile ESM and declarations with TypeScript. Ensure the package exports only
browser-safe modules and includes `dist`, `README.md`, and `LICENSE`. Reject the
smoke bundle if esbuild's metafile contains an external `node:` import or a Node
built-in module name.

- [ ] **Step 4: Verify package artifacts**

Run:

```bash
npm --prefix packages/daytrace-core run typecheck
npm --prefix packages/daytrace-core run build
npm --prefix packages/daytrace-core pack
npm --prefix packages/daytrace-core run smoke:browser
```

Expected: PASS; tarball lists only intended package files, ESM imports in a fresh
consumer, and esbuild produces a browser bundle without Node polyfills.

- [ ] **Step 5: Commit**

```bash
git add packages/daytrace-core
git commit -m "build: package browser-compatible daytrace core"
```

### Task 12: Polish Root and npm Documentation

**Files:**
- Rewrite: `README.md`
- Create: `packages/daytrace-core/README.md`
- Modify: `packages/daytrace-core/package.json`

**Interfaces:**
- Consumes: final install commands and public TypeScript signatures.
- Produces: accurate repository and npm landing pages.

- [ ] **Step 1: Draft the root README in product-first order**

Lead with the ActivityWatch-to-journal outcome and privacy boundary. Follow with
Python and npm installation, CLI and browser/Electron examples, pipeline,
two-stage AI flow, injected adapter example, API table, schemas/failures,
development commands, and future desktop planning links.

- [ ] **Step 2: Add a complete npm integration example**

```ts
import {
  collectDay,
  renderDigestMarkdown,
  summarizeBundleOrFallback,
} from "@jmoraispk/daytrace";

const bundle = await collectDay({
  day: "2026-09-10",
  timezoneName: "Europe/Lisbon",
  server: "http://127.0.0.1:5600",
  transport: activityWatchTransport,
  signal: controller.signal,
  onProgress: ({ stage, elapsedSeconds }) => updateStatus(stage, elapsedSeconds),
});

const result = await summarizeBundleOrFallback(bundle, aiProvider);
if (result.kind === "ai") {
  const markdown = renderDigestMarkdown(bundle, result.digest, result.provenance);
}
```

Explain that `activityWatchTransport`, `aiProvider`, `controller`, and
`updateStatus` are host-owned implementations, and provide their interface
signatures immediately below the example.

- [ ] **Step 3: Write the focused npm README**

Document `npm install @jmoraispk/daytrace`, ESM-only behavior, browser/Electron support,
zero runtime dependencies, public exports, cancellation, progress, privacy,
provider validation, deterministic fallback, and schema compatibility. State
explicitly that the library includes no API key handling, UI, vault access,
scheduling, or Node runtime access.

- [ ] **Step 4: Verify all documented commands and exports**

Run Python CLI help, TypeScript typecheck, and a TypeScript compile of README
examples stored as test fixtures or smoke inputs. Search the docs for stale
`0.3.6` commands and nonexistent exported names.

- [ ] **Step 5: Commit**

```bash
git add README.md packages/daytrace-core/README.md packages/daytrace-core/package.json
git commit -m "docs: document Python and TypeScript daytrace"
```

### Task 13: CI and Synchronized 0.4.0 Metadata

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Modify: `src/daytrace/__init__.py`
- Modify: `uv.lock`
- Modify: `packages/daytrace-core/package.json`
- Modify: `packages/daytrace-core/package-lock.json`
- Modify: `README.md`
- Modify: `tests/fixtures/cross-language/*`
- Test: existing Python version tests plus package metadata checks.

**Interfaces:**
- Consumes: final Python and TypeScript trees.
- Produces: synchronized version metadata and release-blocking CI.

- [ ] **Step 1: Add a failing synchronized-version assertion**

```py
def test_python_and_npm_versions_are_synchronized() -> None:
    npm = json.loads(Path("packages/daytrace-core/package.json").read_text())
    assert daytrace.__version__ == npm["version"] == "0.4.0"
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_version_parity.py -v`  
Expected: FAIL while Python still reports 0.3.6.

- [ ] **Step 3: Bump all version metadata to 0.4.0**

Update Python metadata, package metadata, lockfiles, and pinned README examples.
Run `uv lock` and `npm --prefix packages/daytrace-core install --package-lock-only`
to regenerate lock metadata. Then run the Python fixture writer and confirm that
the only expected fixture changes are synchronized `daytrace_version` fields.

- [ ] **Step 4: Add the Node CI job**

Use `actions/setup-node@v6` with Node 24 and npm caching. Run
`npm ci`, typecheck, tests, build, pack, and browser smoke from
`packages/daytrace-core/`. Keep the Python OS/version matrix unchanged.

- [ ] **Step 5: Verify GREEN locally**

Run:

```bash
uv sync --frozen --all-groups
uv run pytest
uv build --no-sources
npm --prefix packages/daytrace-core ci
npm --prefix packages/daytrace-core run typecheck
npm --prefix packages/daytrace-core test
npm --prefix packages/daytrace-core run build
npm --prefix packages/daytrace-core pack
npm --prefix packages/daytrace-core run smoke:browser
```

Expected: all commands PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml pyproject.toml src/daytrace/__init__.py uv.lock README.md packages/daytrace-core tests/test_version_parity.py
git commit -m "release: prepare synchronized 0.4.0 packages"
```

### Task 14: Final Verification, Publication, Push, and Tag

**Files:**
- Verify: entire repository and built artifacts.
- Produce: PyPI wheel/sdist and npm tarball; no source changes unless verification exposes a defect.

**Interfaces:**
- Consumes: authenticated PyPI and npm identities and the verified release commit.
- Produces: public `daytrace==0.4.0`, public `daytrace@0.4.0`, pushed `main`, and `v0.4.0`.

- [ ] **Step 1: Run fresh release verification**

Run the complete Python and TypeScript command sequence from Task 13 again.
Inspect `git diff --check`, `git status --short`, Python wheel contents, npm
tarball contents, versions, exported declaration surface, and esbuild metafile.

- [ ] **Step 2: Recheck remote package state and credentials**

Run:

```bash
npm whoami
npm view daytrace version
```

Expected before the first npm release: authenticated user `jmoraispk`; package
still absent. Check PyPI to confirm 0.4.0 is not already published.

- [ ] **Step 3: Publish Python artifacts**

Load only `UV_PUBLISH_TOKEN` from the authorized outer `.env` file without
printing it. Publish exactly the 0.4.0 wheel and sdist with `uv publish`.

- [ ] **Step 4: Publish npm artifact**

From `packages/daytrace-core/`, run `npm publish --access public` against the
verified tarball/package contents. Do not publish if the package name changed
ownership or the authenticated account is no longer `jmoraispk`.

- [ ] **Step 5: Verify clean registry installations**

Use isolated temporary environments to import `daytrace==0.4.0` from PyPI and
`daytrace@0.4.0` from npm. For npm, bundle the registry-installed package for a
browser target again and import `DAYTRACE_VERSION`.

- [ ] **Step 6: Push and tag**

```bash
git push origin main
git tag v0.4.0
git push origin v0.4.0
```

Verify remote `main` and tag resolve to the release commit.

- [ ] **Step 7: Report the release**

Report:

- Python package `daytrace==0.4.0` and `pip install daytrace==0.4.0`;
- npm package `@jmoraispk/daytrace@0.4.0` and `npm install @jmoraispk/daytrace@0.4.0`;
- public TypeScript API;
- Python and TypeScript test counts;
- build, pack, and browser smoke results;
- PyPI/npm publication results;
- release commit and tag;
- any deliberate differences from Python, including camelCase in-memory
  TypeScript property names while serialized schema fields remain unchanged.

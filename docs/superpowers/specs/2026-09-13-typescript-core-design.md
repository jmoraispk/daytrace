# Browser-Compatible TypeScript Core Design

**Date:** 2026-09-13  
**Status:** Approved

## Objective

Add a browser-compatible TypeScript implementation of DayTrace's reusable core
without disturbing the existing Python library or CLI. The TypeScript package
will be published publicly to npm as `daytrace`. The Python and npm
distributions will share version `0.4.0` for this release.

The immediate consumer is the Obsidian Second Brain plugin. The package must
also remain usable by other browser and Electron applications without importing
Obsidian concepts or Node-specific capabilities.

## Scope

Create a standalone npm package at `packages/daytrace-core/` that ports the
current Python pipeline:

- ActivityWatch normalization and collection orchestration;
- AFK removal;
- sanitization, generated-text sanitization, and secret detection;
- overlapping-source fusion;
- session construction and episode compaction;
- diagnostics;
- deterministic Markdown and JSON rendering;
- AI summary planning, chunking, repair, and merging;
- structured-response, evidence, allocation, and privacy validation;
- AI Markdown and JSON rendering;
- deterministic fallback behavior.

The Python implementation remains the semantic reference and its CLI remains
intact. This project does not add Obsidian-specific code, vault paths, UI,
scheduling, subprocesses, Node built-ins, or a Git submodule. No personal
ActivityWatch data will be committed.

## Distribution and Versioning

The package source lives at `packages/daytrace-core/`, but its public npm name is
`daytrace`:

```bash
pip install daytrace==0.4.0
npm install daytrace@0.4.0
```

The package exports ESM JavaScript and TypeScript declarations. It has no runtime
npm dependencies. Development-only tooling may include TypeScript, Vitest, and
esbuild. One repository tag, `v0.4.0`, identifies the synchronized Python and
TypeScript release.

## Architecture

The TypeScript source mirrors the Python module boundaries so semantic drift can
be located and reviewed directly:

```text
packages/daytrace-core/
├── package.json
├── README.md
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── models.ts
│   ├── time.ts
│   ├── source.ts
│   ├── normalize.ts
│   ├── transform.ts
│   ├── sanitize.ts
│   ├── fusion.ts
│   ├── sessionize.ts
│   ├── episode.ts
│   ├── diagnostics.ts
│   ├── cloud-privacy.ts
│   ├── prompts.ts
│   ├── summarize.ts
│   ├── summary-diagnostics.ts
│   ├── json-output.ts
│   ├── markdown.ts
│   └── report.ts
└── test/
```

The modules contain no ambient access to the network, filesystem, process,
environment variables, or credential storage. Network operations occur only
through interfaces supplied by the application.

### Data model

Public domain values are readonly TypeScript interfaces composed of JSON-safe
values. Dates use `YYYY-MM-DD`, timestamps use timezone-aware ISO 8601 strings,
durations use seconds, and enumerations use the same string values as Python.

Timestamp calculations preserve ActivityWatch's fractional seconds. Local-day
resolution uses standard browser `Intl` time-zone functionality and produces
half-open day windows. Cross-language fixtures cover ordinary days, spring DST
transitions, and autumn DST transitions.

The TypeScript implementation preserves the current schemas and meanings,
including:

- `daytrace.episode-bundle.v1`;
- `daytrace.workstream-report.v2`;
- `daytrace.summary-request.v2`;
- `daytrace.workstream-digest.v2`;
- workstream merge, diagnostics, and AI-failure schemas.

Object key order and newline conventions are deterministic where they affect
rendered JSON or Markdown parity.

## Injected Boundaries

### ActivityWatch

`collectDay(options)` is asynchronous and accepts an injected ActivityWatch HTTP
interface. The interface receives a relative path, encoded query values, and an
optional `AbortSignal`, then returns decoded JSON. The application decides how
to perform the request. This supports browser `fetch`, Electron bridges, and
Obsidian's request API without adding a direct dependency on any of them.

DayTrace owns server URL validation, ActivityWatch endpoint construction,
response-shape conversion, collection order, and privacy-safe error mapping.
The injected client owns only transport.

### AI provider

The AI provider interface receives a request created by DayTrace containing:

- the chunk or merge pass;
- the minimized structured payload;
- the fixed prompt for that pass;
- the strict structured-response schema;
- an optional `AbortSignal` and content-free progress callback.

It returns structured payload data, provider/model identifiers, optional token
usage, and optional safe opaque request/response identifiers. It cannot access
the ActivityWatch client through the provider interface. DayTrace does not ship
or read API keys; the consuming application owns provider credentials.

## Public API

The root ESM entry point exports the following high-level functions:

- `collectDay(options)`;
- `buildSummaryPlan(bundle)`;
- `summarizeBundle(bundle, provider, plan?, options?)`;
- `summarizeBundleOrFallback(bundle, provider, plan?, options?)`;
- `renderEpisodeJson(bundle, options?)`;
- `renderEpisodeMarkdown(bundle, options?)`;
- `renderDigestJson(bundle, digest, provenance, options?)`;
- `renderDigestMarkdown(bundle, digest, provenance, options?)`;
- `renderSummaryFailureJson(failure)`;
- `DAYTRACE_VERSION`.

It also exports the reusable deterministic stages:

- `normalizeEvents`;
- `removeAfk`;
- `sanitizeRecords`;
- `fuseObservations`;
- `sessionize`;
- `compactSessions`;
- `validateDigest`;
- `validateMerge`;
- `validateFinalAllocation`.

The package exports the relevant domain and injected-interface types, plus
`SYSTEM_PROMPT` and `MERGE_SYSTEM_PROMPT` so provider adapters can be inspected
and tested. Internal helpers remain unexported unless a consumer contract or
parity test requires them.

### Strict and fallback summary flows

`summarizeBundle` follows the Python core behavior: it validates each provider
response and throws a typed, content-free error on provider, schema, evidence,
allocation, or privacy failure.

`summarizeBundleOrFallback` is the application-facing orchestration helper. It
returns a discriminated result:

- an AI result containing the validated digest and provenance; or
- a deterministic result containing the original episode bundle and a safe
  failure description suitable for diagnostics.

It never returns unchecked model prose. Rendering remains explicit so consuming
applications choose Markdown, JSON, or their own presentation.

## Cancellation and Progress

Collection and summarization accept an optional `AbortSignal`. Cancellation is
checked before and after injected calls and between long-running stages. An
abort is not converted into an AI failure or deterministic fallback; it remains
an explicit cancellation result for the host application.

Progress callbacks are optional and content-free. Events use fixed stages such
as:

- `activitywatch:info`;
- `activitywatch:buckets`;
- `activitywatch:events`;
- `pipeline:normalize`;
- `pipeline:sanitize`;
- `pipeline:fuse`;
- `pipeline:sessions`;
- `pipeline:episodes`;
- `summary:chunk`;
- `summary:repair`;
- `summary:merge`;
- `complete`.

Events may contain counts, current/total indices, and elapsed seconds. They do
not contain bucket IDs, event IDs, titles, URLs, paths, prompt bodies, response
bodies, or credentials. Exceptions and diagnostics follow the same
content-free rule.

## Privacy and Validation

The TypeScript port maintains the Python privacy boundary:

1. Normalize and clip ActivityWatch events.
2. Remove AFK intervals.
3. Sanitize text, paths, URLs, emails, and secret-like content.
4. Minimize episode content for cloud transfer.
5. Run a final recursive privacy assertion immediately before provider calls.
6. Strictly validate provider structure, evidence IDs, and global allocation.
7. Sanitize and secret-scan generated text before returning it.
8. Expose only allow-listed, content-free failure diagnostics.

Captured text is always treated as untrusted data. It never becomes an
instruction or tool input outside the fixed structured provider request.

## Cross-Language Parity

Synthetic fixtures are the contract between implementations. Fixtures contain
only invented applications, titles, URLs, projects, paths, and provider
responses. They cover:

- normalization, clipping, ordering, and non-positive events;
- AFK subtraction and focused duration;
- text/path/URL sanitization and secret detection;
- overlapping window, browser, and editor signals;
- session boundaries and IDs;
- episode anchors, compaction, IDs, and duration conservation;
- diagnostics and warning counts;
- ordinary and DST-boundary day windows;
- deterministic episode JSON and Markdown;
- summary request chunking and minimized payloads;
- digest, evidence, merge, and final-allocation validation;
- repair behavior and multi-chunk merging;
- AI JSON and Markdown;
- privacy-safe AI failure artifacts and deterministic fallback.

A Python fixture generator or adapter feeds the current Python implementation
and writes committed expected artifacts. Python tests verify that the reference
still produces those artifacts. TypeScript tests consume the same inputs and
must match the expected structures and rendered text. Intentional differences
must be documented in both the fixture and release notes; the initial target is
no deliberate semantic difference.

## Build and Browser Smoke Test

The package build produces ESM JavaScript and `.d.ts` declarations in `dist/`.
The npm package contains only required distribution files, its package README,
license, and package metadata.

The release-blocking smoke test:

1. Runs `npm pack`.
2. Installs the resulting tarball in a temporary consumer project.
3. Imports the public API.
4. Bundles that consumer with esbuild using `platform: "browser"`.
5. Supplies no Node polyfills or aliases.
6. Verifies the bundle contains no unresolved Node built-in imports.

CI keeps the existing Python matrix and adds a Node job that runs TypeScript
type-checking, unit/parity tests, build, pack inspection, and the browser smoke
test.

## Documentation

The root README will be rewritten around the products that exist now rather
than leading with future desktop plans. Its order will be:

1. Concise purpose and privacy promise.
2. Python CLI and TypeScript library installation.
3. Quick-start examples.
4. Deterministic pipeline and AI two-stage flow.
5. Second Brain integration with injected ActivityWatch and AI adapters.
6. Public TypeScript API.
7. Schemas, privacy, and diagnostics.
8. Development, parity, build, and release commands.
9. Future desktop architecture and planning links.

The npm package includes a focused README with installation, browser/Electron
constraints, adapter examples, API documentation, cancellation/progress usage,
privacy guarantees, and schema/version compatibility.

## Release Workflow

The synchronized 0.4.0 release is complete only after:

1. All Python tests pass.
2. All TypeScript unit and parity tests pass.
3. Python and npm builds succeed.
4. The packed npm artifact passes the browser/esbuild smoke test.
5. Package contents and versions are inspected.
6. `daytrace==0.4.0` is published and clean-installed from PyPI.
7. `daytrace@0.4.0` is published and clean-installed from npm.
8. The release commit is pushed to `main`.
9. `v0.4.0` is pushed.
10. The final report lists package names, install commands, public API, test and
    build results, publication locations, and any deliberate Python/TypeScript
    differences.

The authenticated npm identity at design time is `jmoraispk`. Publication is
explicitly authorized. The npm name `daytrace` was unclaimed when checked on
2026-09-13, but final availability must be verified again immediately before
publication.

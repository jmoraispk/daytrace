# ActivityWatch Day Summary CLI Design

Date: 2026-09-10
Status: Approved direction; ready for implementation planning

Live compatibility baseline: ActivityWatch `aw-server-rust` v0.13.2

## Goal

Build a small, headless CLI that reads one calendar day from a locally running
ActivityWatch server and writes a deterministic Markdown activity summary. The
prototype does not capture activity itself, use an LLM, or persist a second
copy of ActivityWatch data.

Example:

```text
daytrace activitywatch --date 2026-09-10 --project daytrace
```

Markdown is written to stdout so it can be redirected into a file, piped to
another program, or consumed later by the user's second-brain project.

## Approaches Considered

### Direct REST client in Rust (selected)

Call ActivityWatch's localhost API directly, normalize raw watcher events, and
render Markdown in one binary.

- Small deployment surface and no Python/Node runtime.
- Keeps the ActivityWatch dependency at its HTTP boundary.
- Straightforward to extract into a reusable Rust library later.
- Requires us to maintain compatibility with the subset of the API we use.

### ActivityWatch query API

Send ActivityWatch query-language programs to the server and render their
results.

- Can reduce data transferred to the CLI.
- Couples the prototype more tightly to ActivityWatch query semantics and
  makes its transformation logic harder to test independently.

### Script using an ActivityWatch client package

Use Python and the ActivityWatch client package for the fastest throwaway
implementation.

- Quick initial development.
- Adds a runtime and packaging burden that conflicts with the intended
  efficient cross-platform utility.

## Command Surface

```text
daytrace activitywatch [OPTIONS]

Required:
  --date YYYY-MM-DD

Optional:
  --project TEXT             Case-insensitive project filter
  --server URL               Default: http://127.0.0.1:5600
  --timezone IANA_ZONE       Default: system timezone
  --output PATH              Default: stdout
```

The first version has one output format: deterministic Markdown. It does not
require an API key or network access beyond the explicitly configured
ActivityWatch server.

## Data Acquisition

1. Resolve the selected local day to an exact half-open time range `[start,
   end)` in the requested or system timezone.
2. Verify the server with `GET /api/0/info`.
3. Discover buckets with `GET /api/0/buckets/` rather than assuming hostnames
   or bucket IDs.
4. Fetch events for the selected range from relevant raw watcher buckets with
   `GET /api/0/buckets/{bucket_id}/events?start=...&end=...`.
5. Recognize standard bucket types where available:
   - current window: application and title
   - AFK status: active or away intervals
   - browser tab: title and URL-derived host
   - editor: file, project, and language
6. Ignore unknown bucket types safely in the initial release and report their
   count in diagnostics only.

No ActivityWatch database files are opened directly. The CLI only uses the
documented localhost HTTP interface.

## Normalization and Filtering

Each supported event becomes an internal record containing:

- source bucket and source kind
- clipped start and end timestamps
- application
- title
- project
- file path
- URL host
- language

The client does not rely on server response order: v0.13.2 returns bounded
event queries newest-first. Records are reordered by start time, then source
bucket ID, then ActivityWatch event ID. Invalid timestamps and non-positive
durations are skipped with a warning. Events crossing the day boundary are
clipped to it.

The client enforces the half-open range itself even though v0.13.2 also clips
cross-boundary events. In particular, that server can return an event starting
exactly at the requested end timestamp with a zero duration; the client drops
that record.

AFK intervals are unioned first. Away portions are subtracted from other
records, splitting records when necessary. This ensures the timeline describes
active computer use rather than merely recorded window duration.

When `--project` is present, a record matches when the supplied text occurs as
a Unicode case-insensitive substring in any of: project, application, title,
file path, URL host, or bucket ID. This deliberately simple rule works with raw
watcher data and requires no separate project configuration for the prototype.

Within the same source bucket, consecutive records with identical normalized
content are merged when the gap is at most 60 seconds. Records from different
watchers are never added together as independent durations because they can
overlap.

## Deterministic Markdown

Given identical API responses, command arguments, and timezone data, the CLI
must produce byte-identical output. It uses fixed headings, field order,
sorting, duration rounding, and escaping. It contains no generation timestamp
and makes no LLM call.

Example shape:

```markdown
# Activity summary — 2026-09-10

Project filter: `daytrace`
Timezone: `America/Los_Angeles`

## Overview

- Active matched time: 2h 14m
- Timeline entries: 12
- Sources: Current window, Editor

## Timeline

- 09:02–09:27 (25m) — Visual Studio Code — daytrace: ActivityWatch client
- 09:28–09:41 (13m) — Firefox — ActivityWatch API documentation

## Applications

- Visual Studio Code — 1h 48m
- Firefox — 26m
```

The overview and application totals use current-window events as the primary
duration source, after AFK subtraction. If no current-window bucket exists, the
report labels totals as unavailable rather than double-counting simultaneous
browser and editor events.

Full URLs and URL query strings are not printed. A URL host can be used for
matching and display. File paths are displayed in compact form, with the home
directory replaced by `~`.

## Errors and Empty Days

- An unreachable server returns a non-zero exit code and a concise instruction
  to start ActivityWatch or change `--server`.
- An unsupported API response returns a non-zero exit code naming the failing
  endpoint without dumping personal event content.
- A valid day with no matching activity returns exit code zero and a valid
  Markdown document containing `No matching activity.`
- Warnings go to stderr; Markdown alone goes to stdout.

## Internal Structure

The binary remains thin over a reusable library boundary:

```text
CLI arguments
    -> ActivityWatch HTTP client
    -> raw event normalization
    -> AFK/project filtering and merging
    -> report model
    -> deterministic Markdown renderer
```

The report model is serializable but JSON output is intentionally deferred.
The second-brain project can later call the library directly, execute the CLI,
or schedule the command and ingest its Markdown without changing extraction
semantics.

## Verification Strategy

- Fixture tests for bucket discovery and every supported watcher schema.
- Boundary tests for local-midnight ranges, daylight-saving changes, clipped
  events, AFK interval subtraction, and overlapping watcher sources.
- Golden-file tests for byte-stable Markdown.
- CLI tests for stdout/stderr separation, empty days, unreachable servers, and
  output files.
- Live smoke test against ActivityWatch once a local server is available and
  the user explicitly permits reading a chosen day's activity.

The connection, bucket metadata, standard watcher event shapes, bounded query
behavior, and response ordering have been verified against an isolated
ActivityWatch v0.13.2 testing server with synthetic `currentwindow`,
`afkstatus`, `app.editor.activity`, and `web.tab.current` buckets.

## Explicitly Deferred

- UI and background capture
- LLM summaries
- direct access to ActivityWatch's database files
- ActivityWatch query-language programs
- GitHub synchronization
- automatic second-brain writes
- custom watcher schemas and configurable project rules

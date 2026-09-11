# ActivityWatch Day Summary CLI Design

Date: 2026-09-10
Status: Approved direction; ready for implementation planning

Live compatibility baseline: ActivityWatch `aw-server-rust` v0.13.2

## Goal

Build a small, headless CLI that reads one calendar day from a locally running
ActivityWatch server and writes a deterministic Markdown activity summary. The
prototype does not capture activity itself, use an LLM, or persist a second
copy of ActivityWatch data. It is distributed as a pure-Python wheel and run
with `uv` on Linux, macOS, and Windows.

Example:

```text
daytrace activitywatch --date 2026-09-10 --project daytrace
```

Markdown is written to stdout so it can be redirected into a file, piped to
another program, or consumed later by the user's second-brain project.

## Approaches Considered

### Python with the official `aw-client` package (selected)

Use ActivityWatch's primary client library to discover buckets and fetch raw
events, then normalize and render them in a small Python package.

- Fastest route to a working, testable prototype.
- Uses ActivityWatch's supported `get_info`, `get_buckets`, and `get_events`
  client interface rather than recreating it.
- Produces a cross-platform, pure-Python wheel that `uv` can install or run in
  an isolated environment.
- Gives the second-brain project a normal importable Python API.
- Has higher startup and memory overhead than a native binary, but that is
  immaterial for a command that runs once and exits.

### Direct REST client in Python

Use a general HTTP library to call the verified ActivityWatch REST endpoints
without depending on `aw-client`.

- Gives complete control over HTTP behavior and dependency versions.
- Makes Daytrace responsible for compatibility with ActivityWatch's evolving
  API even though an official Python client already exists.

### Native Rust CLI

Call ActivityWatch directly and ship a standalone native executable.

- Has lower startup overhead and can later share code with a Rust/Tauri desktop
  collector.
- Takes longer to implement and package, while offering little practical
  benefit for this short-lived reporting command.

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

From a source checkout:

```text
uv sync
uv run daytrace activitywatch --date 2026-09-10 --output summary.md
```

After publication, users can run it without permanent installation:

```text
uvx daytrace activitywatch --date 2026-09-10 --output summary.md
```

## Data Acquisition

1. Resolve the selected local day to an exact half-open time range `[start,
   end)` in the requested or system timezone.
2. Create an `ActivityWatchClient` from the host, port, and protocol parsed
   from `--server`, then verify it with `get_info()`.
3. Discover buckets with `get_buckets()` rather than assuming hostnames or
   bucket IDs.
4. Fetch events for the selected range from relevant raw watcher buckets with
   `get_events(bucket_id, start=..., end=...)`.
5. Recognize standard bucket types where available:
   - current window: application and title
   - AFK status: active or away intervals
   - browser tab: title and URL-derived host
   - editor: file, project, and language
6. Ignore unknown bucket types safely in the initial release and report their
   count in diagnostics only.

No ActivityWatch database files are opened directly. The CLI only uses the
official client library over ActivityWatch's localhost HTTP interface. The
query-language API is not used in this prototype.

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

For overview and application totals, overlapping current-window records are
partitioned at every start and end boundary. Each segment is assigned to the
covering record ordered first by bucket ID and event ID. This deterministic
tie-breaker prevents multi-bucket data from inflating total time; multi-device
selection remains deferred.

## Deterministic Markdown

Given identical API responses, command arguments, and timezone data, the CLI
must produce byte-identical output. It uses fixed headings, field order,
sorting, duration rounding, and escaping. It contains no generation timestamp
and makes no LLM call.

Files written with `--output` use UTF-8 without a byte-order mark and LF line
endings on every operating system.

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

The console entry point remains thin over a reusable Python library boundary:

```text
CLI arguments
    -> ActivityWatch client adapter
    -> raw event normalization
    -> AFK/project filtering and merging
    -> report model
    -> deterministic Markdown renderer
```

The package uses focused modules under `src/daytrace/` for the CLI, the
ActivityWatch adapter, domain models and transforms, and Markdown rendering.
The public function
`daytrace.activitywatch.summarize_day(date, project=None, ...) -> str` returns
the same Markdown emitted by the CLI. The report model is serializable but JSON
output is intentionally deferred.

The second-brain project can import that function, execute the CLI, or schedule
the command and ingest its Markdown without changing extraction semantics.

## Packaging and Runtime

- Python 3.11 or newer.
- Standards-based `pyproject.toml` using the `uv_build` backend and a `daytrace`
  console entry point.
- Runtime dependency on `aw-client`; its compatible version range is recorded
  in `pyproject.toml` and the exact development version in `uv.lock`.
- Runtime dependency on `tzlocal` to discover the system's IANA timezone name
  consistently across supported operating systems.
- Conditional `tzdata` dependency on platforms such as Windows that do not
  provide an IANA timezone database.
- Standard-library `argparse`, `datetime`, `zoneinfo`, and `urllib.parse` for
  the remaining CLI and transformation needs.
- `uv build --no-sources` produces the source distribution and universal
  `py3-none-any` wheel.

Rust/Tauri remains an option for the future continuous desktop collector. The
ActivityWatch summary package does not need to share that implementation
language.

## Verification Strategy

- `pytest` fixture tests for bucket discovery and every supported watcher
  schema through a fake ActivityWatch adapter.
- Boundary tests for local-midnight ranges, daylight-saving changes, clipped
  events, AFK interval subtraction, and overlapping watcher sources.
- Golden-file tests for byte-stable Markdown.
- CLI tests for stdout/stderr separation, empty days, unreachable servers, and
  output files.
- Live smoke test against ActivityWatch once a local server is available and
  the user explicitly permits reading a chosen day's activity.
- Wheel build and isolated install/run tests with `uv`.

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
- standalone native executables

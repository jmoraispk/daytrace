# Daytrace

Daytrace is a privacy-first desktop utility that turns a person's day into a
searchable text journal. Screen, microphone, keyboard activity, and system
context are independent opt-ins. Captured media is processed ephemerally and
discarded; the durable record contains text and structured metadata only.

This repository now includes a headless ActivityWatch summary prototype. The
broader cross-platform capture application remains in the product and
architecture planning phase.

## ActivityWatch workstream digest

The Python CLI reads a selected day from an already-running ActivityWatch
instance, sanitizes and fuses its watcher data, and reconstructs project-neutral
activity sessions, then compacts them into project-neutral activity episodes.
It can stop there with a fully local deterministic report, or—only when
explicitly requested—send minimized episodes to OpenAI to
infer broad workstreams, topics, and evidence-backed apparent achievements.

DayTrace's inferred workstreams are not canonical project definitions. They are
a useful daily handoff that an Obsidian Second Brain plugin can later map to the
projects defined in the vault. This keeps DayTrace useful without access to the
vault and leaves durable project ownership in Obsidian.

Prerequisites: install and run ActivityWatch, then install `uv`. On Windows:

```powershell
winget install --id=astral-sh.uv -e
```

From a source checkout:

```powershell
uv sync
uv run daytrace activitywatch --date 2026-09-10 --output daytrace.md
```

After the package is published, the equivalent one-off workflows are:

```powershell
# Project-neutral compact episodes; no model or key
uvx daytrace@latest activitywatch --date 2026-09-10 --output daytrace.md

# AI-assisted inferred workstreams; key entered in a hidden prompt
uvx --refresh --link-mode=copy daytrace@0.3.2 activitywatch `
  --date 2026-09-10 `
  --summary ai `
  --provider openai `
  --model gpt-5.6-terra `
  --debug-output daytrace-ai-failure.json `
  --output daytrace.md

# Structured handoff for the future Second Brain plugin
uvx daytrace@latest activitywatch --date 2026-09-10 --summary ai `
  --provider openai --model YOUR_MODEL --format json --output daytrace.json
```

The deterministic mode needs no API key. It emits compact episodes with exact
active duration while using current-window events as the foreground-time
authority; simultaneous browser and editor events enrich those episodes rather
than double-counting time. Repeated assistant, terminal, new-tab, and file-manager
transitions are aggregated around compatible work anchors. Short activity is
shown as `<1m`.

AI mode is a separate second stage. Before any cloud request, DayTrace reports
the number of compact episodes, planned summary chunks and merge call, total
initial request size, included data categories, provider, and model, then asks
for confirmation. Most compact days use one call; unusually large days are
partitioned at episode boundaries and receive one constrained merge call. Only
after consent does DayTrace request the OpenAI API key through a hidden prompt.
The key is held in memory only. Never put a key in command-line arguments or
paste it into support logs. OpenAI Responses API calls set `store=False`.

The model returns structured data that DayTrace validates locally. Each topic
and visible achievement must cite a supplied episode, every episode must be
allocated exactly once, and model-produced text receives another secret scan.
Durations always come from the deterministic local trace. If an explicitly
requested AI call or response fails, DayTrace writes the deterministic fallback
and exits with status 2. With `--debug-output`, it also writes a versioned JSON
support artifact containing only allow-listed structural metadata: failure
codes, response shape counts, supplied episode IDs, and safe opaque provider
identifiers. It never includes model-generated prose, ActivityWatch titles,
request bodies, response bodies, or the API key. Review this artifact before
sharing it, as you would any diagnostic file.

Useful local modes:

- `--details` adds sanitized episode membership and evidence identifiers.
- `--raw` appends the fine-grained sanitized session/slice audit trail and cannot be combined with
  `--details` or AI mode.
- `--diagnostics` prints only aggregate, content-free counts and coverage.
- `--format json` emits a versioned structured artifact suitable for another
  plugin; Markdown is the default.
- `--yes` confirms the disclosed cloud send for non-interactive AI automation,
  but the API key is still collected separately through the hidden prompt.

To capture the sanitized raw sessions needed to improve DayTrace's episode
compression in a later release:

```powershell
uvx --refresh --link-mode=copy daytrace@0.3.2 activitywatch `
  --date 2026-09-10 `
  --format json `
  --raw `
  --output daytrace-raw.json
```

Raw output has passed DayTrace's sanitizer, but it still describes personal
activity and can contain sensitive context. Review it before sharing.

If Windows reports that uv cannot hardlink across cache and target filesystems,
use `uvx --link-mode=copy daytrace@latest ...`; this affects installation speed,
not DayTrace output or correctness.

Python callers—including a future second-brain integration—can use the same
project-neutral collection and deterministic renderer directly:

```python
from datetime import date

from daytrace.activitywatch import collect_day, summarize_day

bundle = collect_day(date(2026, 9, 10))
markdown = summarize_day(date(2026, 9, 10))
```

Daytrace reads ActivityWatch through `http://127.0.0.1:5600` by default. It
does not retain images, audio, video, raw browser URLs, query strings, source
event IDs, source bucket IDs, or a second copy of ActivityWatch events. Use
`--server` for another ActivityWatch endpoint and `--timezone` for an explicit
IANA timezone such as `America/Los_Angeles`.

DayTrace deliberately does not read the Obsidian vault or decide canonical
project names. Its workstream digest is designed as the handoff to the Second
Brain plugin, which can map the evidence-based daily workstreams onto project
definitions stored in Obsidian.

## Product decisions

- Local-first: the database and processing stay on the user's computer unless
  the user explicitly configures a cloud provider or export destination.
- All capture sources start off and require separate, informed consent.
- Tauri 2 and Rust are the recommended desktop stack, with a small React/Vite
  interface that normally stays hidden behind a tray icon.
- Accessibility text is preferred over screenshots. OCR is a fallback, and
  image buffers are destroyed after extraction.
- Microphone audio is held only in bounded memory, segmented with voice
  activity detection, transcribed, and discarded.
- Keyboard capture defaults to activity signals only, not key content. An
  advanced typed-text mode is a later, separately consented feature with
  password and deny-list suppression.
- SQLite, B-tree time dimensions, and FTS5 provide the hierarchical timeline
  and full-text search. Captured media and vector embeddings are not stored.
- The first release supports BYOK and local providers. A hosted inference
  gateway can later fund the project without locking users into the service.

## Plan

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model and search](docs/DATA_MODEL.md)
- [Privacy and security](docs/PRIVACY_SECURITY.md)
- [Product and UX specification](docs/PRODUCT_UX.md)
- [Screenpipe reuse audit](docs/SCREENPIPE_REUSE.md)
- [ActivityWatch integration research](docs/ACTIVITYWATCH_INTEGRATION_RESEARCH.md)

## Proposed repository shape

```text
apps/
  desktop/                 Tauri window, tray, onboarding, settings
crates/
  daytrace-core/           orchestration, policies, domain events
  daytrace-capture/        platform-neutral capture traits
  daytrace-platform-*/     macOS, Windows, and Linux adapters
  daytrace-extract/        accessibility, OCR, VAD, transcription
  daytrace-store/          SQLite migrations, FTS, retention
  daytrace-summary/        segmentation and provider-neutral summaries
  daytrace-sync/           deterministic export and GitHub sync
  daytrace-secrets/        OS credential-store abstraction
extensions/
  browser/                 optional Chromium/Firefox tab metadata bridge
docs/
```

## Target outcome

The v1 release is a signed, auto-updating macOS, Windows, and Linux desktop app
that can run for an eight-hour day without retaining raw media, recover cleanly
from sleep and device changes, search a local journal, and create an editable
end-of-day summary. See the implementation plan for measurable release gates.

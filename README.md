# Daytrace

Daytrace is a privacy-first desktop utility that turns a person's day into a
searchable text journal. Screen, microphone, keyboard activity, and system
context are independent opt-ins. Captured media is processed ephemerally and
discarded; the durable record contains text and structured metadata only.

This repository now includes a headless ActivityWatch summary prototype. The
broader cross-platform capture application remains in the product and
architecture planning phase.

## ActivityWatch summary prototype

The first executable prototype is a Python CLI that reads a selected day from
an already-running ActivityWatch instance and produces deterministic Markdown.
It does not copy raw events or call an LLM.

Prerequisites: install and run ActivityWatch, then install `uv`. On Windows:

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

The resulting `summary.md` contains an overview, a chronological timeline, and
application totals. A day with no matching activity is still a successful
report and contains `No matching activity.`

After the package is published, the equivalent one-off command will be:

```powershell
uvx daytrace activitywatch --date 2026-09-10 --output summary.md
```

Python callers—including a future second-brain integration—can use the same
deterministic renderer directly:

```python
from datetime import date

from daytrace.activitywatch import summarize_day

markdown = summarize_day(date(2026, 9, 10), project="daytrace")
```

Daytrace reads ActivityWatch through `http://127.0.0.1:5600` by default. It
does not retain images, audio, video, full browser URLs, or a second copy of
ActivityWatch events. Use `--server` for another ActivityWatch endpoint and
`--timezone` for an explicit IANA timezone such as `America/Los_Angeles`.

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

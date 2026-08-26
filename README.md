# Daytrace

Daytrace is a privacy-first desktop utility that turns a person's day into a
searchable text journal. Screen, microphone, keyboard activity, and system
context are independent opt-ins. Captured media is processed ephemerally and
discarded; the durable record contains text and structured metadata only.

This repository is currently in the product and architecture planning phase.

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

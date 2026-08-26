# Daytrace implementation plan

Status: proposed  
Audience: product, design, engineering, security, and release maintainers  
Planning assumption: a small team of three engineers plus part-time design/QA

## 1. Outcome

Daytrace should answer “what did I do, when, and in what context?” without
building a media archive. It runs as a quiet desktop utility, converts opted-in
signals to text close to collection time, stores a local searchable journal,
and produces editable summaries.

Success for v1 means:

- macOS, Windows, and mainstream Linux desktops are supported with explicit
  capability reporting where an OS or compositor cannot provide a feature;
- each source can be enabled, paused, scheduled, filtered, and deleted
  independently;
- screenshots and audio never enter the durable data directory;
- useful entries appear within 30 seconds after processing on reference
  hardware;
- an eight-hour balanced-mode run targets less than 1% average CPU when idle,
  less than 3% average CPU across the day excluding model inference, less than
  250 MB resident memory without an embedded model, and less than 25 MB/day of
  text/metadata in normal office use;
- crashes cannot leave raw capture files behind, and restart does not duplicate
  journal entries;
- search by words, app, source, year/week/day, and time of day is local and
  responsive (p95 below 150 ms over one year / 100,000 entries on the reference
  dataset);
- summaries always link back to the entries that support them and can be
  regenerated, edited, or deleted.

These numbers are acceptance targets to validate with benchmarks, not claims
about an unbuilt product.

## 2. Decisions made now

1. Build a Tauri 2 desktop app with Rust capture and processing libraries and a
   React/Vite UI. The process remains alive in the system tray; closing the
   window hides it rather than stopping collection.
2. Keep the first implementation in one desktop process. Capture, extraction,
   storage, and UI are separate Rust crates/tasks with bounded channels. This
   minimizes baseline memory and makes a supervised sidecar possible later if
   crash isolation proves necessary.
3. Prefer event-driven collection with a maximum-gap timer. “Every five
   minutes” means the maximum time between useful observations while active,
   not unconditional screenshot polling.
4. Keep local SQLite as the source of truth. The “hierarchical index” is a set
   of indexed calendar dimensions plus FTS5, not a fragile directory tree.
5. Keep summaries provider-neutral. Deterministic segmentation and redaction
   happen locally before any model call.
6. Treat GitHub as export/sync, not as the live database. Export deterministic
   daily Markdown and JSONL; do not commit the changing SQLite file.
7. Do not copy current Screenpipe code without a commercial agreement. If
   reuse is approved, pin eligible code to the final audited MIT commit and
   preserve notices. See `SCREENPIPE_REUSE.md`.

## 3. Scope

### v1

- Menu-bar/system-tray operation, launch at login, pause/resume, health state,
  and signed updates.
- Independent toggles for screen-derived text, microphone transcript, keyboard
  activity, window metadata, and idle state.
- Source-specific schedules, app/window deny lists, private mode, and retention.
- Accessibility-first text extraction with OCR fallback.
- Microphone VAD and local transcription, with optional OpenAI-compatible cloud
  transcription only after explicit disclosure.
- Foreground application, safe window title, process identifier, display, idle
  state, and optional browser tab title/URL through an extension.
- Keyboard activity counts and shortcuts without typed content.
- Local timeline, full-text and calendar search, activity segments, and daily
  summaries.
- Local/BYOK model configuration, provider health test, spend ceiling, and clear
  per-request data disclosure.
- Deterministic daily export and optional GitHub sync.
- Per-entry, per-day, source-specific, range, and full-vault deletion.

### Later, behind separate consent

- Typed-text capture with password-field suppression and an always-visible
  indicator.
- Embedded small language model; v1 can support an installed local runtime such
  as an OpenAI-compatible local server to avoid inflating the base installer.
- Speaker diarization, semantic/vector search, multi-device merge, mobile
  capture, team features, and automation APIs.
- A supervised capture sidecar if fault-injection data justifies the extra
  process and platform signing complexity.

### Non-goals

- Employee monitoring, stealth collection, remote activation, or administrator
  access to a person's journal.
- Video/audio playback, screenshot history, or recovery of raw media.
- Inferring productivity, emotion, intent, or employee performance.
- Circumventing protected-content, secure-input, browser, or OS boundaries.
- Treating a private Git repository as a secure vault by itself.

## 4. Collection policy

Capture cadence and summary granularity are separate settings.

| Preset | Active minimum gap | Active maximum gap | OCR behavior | Intended use |
|---|---:|---:|---|---|
| Detailed | 30 seconds | 1 minute | on meaningful visual change | short investigations |
| Balanced (default) | 1 minute | 5 minutes | accessibility first; OCR on fallback/change | everyday use |
| Light | 5 minutes | 10 minutes | foreground window only | low-power devices |
| Hourly | 15 minutes | 60 minutes | one observation per active hour | broad journal |
| Scheduled | chosen preset | chosen preset | only inside allowed blocks | workday-only capture |

Triggers include foreground-app change, window-title change, unlock/resume,
meeting start, speech segment completion, and a typing pause. Debounce noisy
events, enforce the minimum gap, suppress collection while idle, and use the
maximum gap as a fallback. Audio uses voice activity and bounded speech chunks,
not the screen timer. Keyboard activity is aggregated into the current minute.

Summary choices are independent: on demand, end of day, morning/afternoon,
hourly, weekly, or disabled. A scheduled summary runs only after its window has
closed and the device is awake; missed work runs once on the next wake.

## 5. Workstreams and milestones

### Phase 0 — decisions and feasibility (1–2 weeks)

- Ratify the threat model, privacy language, license, supported OS versions,
  reference hardware, and telemetry policy.
- Run focused spikes for macOS ScreenCaptureKit/Accessibility, Windows Graphics
  Capture/UI Automation, and Linux Wayland portals/AT-SPI plus X11 fallback.
- Prove that one frame can be captured into memory, converted to text, zeroed,
  and absent from the data directory after normal exit and forced crash.
- Benchmark accessibility extraction versus OCR and evaluate local speech
  models on representative hardware.
- Inventory the last MIT Screenpipe snapshot and every transitive dependency
  proposed for reuse. Record origin, commit, license, modifications, and owner.

Exit gate: all three operating systems have a working permission/capture spike;
legal approves the reuse strategy; hard performance budgets are documented.

### Phase 1 — foundation and metadata journal (2–3 weeks)

- Create the Rust workspace, Tauri shell, tray menu, autostart, structured local
  logs, crash-safe settings, and database migrations.
- Implement the capture-source trait, bounded event bus, scheduler, backpressure
  policy, health state machine, and source-independent consent records.
- Add foreground app/window metadata, idle detection, timeline UI, FTS search,
  calendar navigation, and deletion.
- Add synthetic capture adapters so CI never records the build machine.

Exit gate: the app records only synthetic and window-metadata events for a full
day, survives sleep/wake and restarts, and passes migration/retention tests.

### Phase 2 — screen-derived text (3–5 weeks)

- Implement accessibility adapters first, with focused-window and selected-
  display scope.
- Add native OCR where practical and an audited cross-platform fallback.
- Add perceptual/text hashing, duplicate suppression, app/window deny lists,
  protected-content failure states, and ephemeral-buffer assertions.
- Build permission repair flows and multi-monitor/hot-plug handling.

Exit gate: the reference corpus meets the agreed extraction accuracy; balanced
mode meets CPU/memory targets; no image artifact is found after crash tests.

### Phase 3 — microphone transcription (3–5 weeks)

- Add device selection, sample-rate normalization, VAD, bounded ring buffers,
  speech chunking, local transcription, and device-change recovery.
- Add microphone-specific schedule, meeting-only mode, language selection, and
  visible tray state.
- Ensure backpressure drops or shortens unprocessed audio rather than spilling
  raw PCM to disk. Store explicit “gap” events when loss occurs.

Exit gate: eight-hour soak, unplug/replug, sleep/wake, silence, device contention,
and crash tests pass; no raw audio artifact remains.

### Phase 4 — segmentation, summaries, and providers (2–4 weeks)

- Merge observations into activity segments using time, app, window, and text
  similarity. Keep source entry IDs as evidence.
- Implement a versioned prompt/schema and provider interface for installed local
  runtimes, BYOK OpenAI-compatible APIs, and the future hosted gateway.
- Add end-of-day editor, summary provenance, retry/idempotency, token/spend
  budgets, and prompt-injection-resistant data delimiters.
- Build a deterministic no-model summary fallback (time ranges, applications,
  and extracted text snippets) so the core product works without AI.

Exit gate: summaries validate against a typed schema, contain evidence links,
and never silently omit provider errors or send data without the configured
policy.

### Phase 5 — keyboard activity, browser bridge, and export (3–4 weeks)

- Aggregate keyboard event counts and recognized shortcuts; do not store raw
  keys. Pause on secure-input/password signals where available.
- Build a Manifest V3 browser extension with optional `tabs` permission and a
  native-messaging bridge. Collect only active-tab title and normalized URL
  according to the user's URL policy; disable in private/incognito browsing by
  default.
- Export one immutable JSONL shard per device/day and one human-readable daily
  Markdown file. Add GitHub App authorization-code flow with PKCE, repository
  selection, least-privilege contents access, OS keychain storage, retries, and
  a visible sync log.
- Add optional client-side encryption for detailed exports. Default GitHub sync
  to summaries only and require a private repository acknowledgement.

Exit gate: multiple devices can sync without rewriting each other's shards;
offline changes converge; credentials never enter logs, SQLite, or exports.

### Phase 6 — hardening and public release (4–6 weeks)

- Conduct privacy/security review, dependency and license scanning, external
  penetration testing, accessibility review, and data-loss recovery exercises.
- Add release CI for signed/notarized macOS, signed Windows installers, and
  AppImage/deb/rpm (plus Flatpak when portal behavior is proven).
- Add signed Tauri updates, reproducible-build notes, SBOMs, checksums, rollback,
  crash opt-in, and a privacy-preserving diagnostics bundle.
- Run a four-week opt-in beta across the supported OS/display/audio matrix.

Exit gate: release criteria in section 8 pass; high-severity findings are fixed;
permission and uninstall/deletion documentation are complete.

At this scope, expect roughly 24–32 engineer-weeks for a strong single-platform
beta and 40–55 engineer-weeks for a credible three-platform v1. With three
engineers, work can overlap into roughly 14–18 calendar weeks, but OS hardening
and signing are likely to control the schedule.

## 6. Engineering sequence inside each feature

Every source follows the same vertical slice:

1. synthetic adapter and contract tests;
2. explicit onboarding consent and OS permission request;
3. bounded in-memory capture;
4. local extraction and redaction;
5. normalized `ObservationDraft` with provenance;
6. transactional persistence and FTS update;
7. timeline/search presentation;
8. pause/delete/retention behavior;
9. performance, sleep/wake, device-change, and forced-crash tests;
10. user-facing diagnostics and permission repair.

This sequence keeps capture from landing before its controls and deletion path.

## 7. Testing strategy

- Unit: policies, calendar dimensions, DST/ISO week edges, redaction, dedupe,
  segmentation, retention, provider budgets, and export determinism.
- Contract: every OS adapter runs the same capability, permission-denied,
  cancellation, timeout, and device-loss suite.
- Golden corpus: synthetic screens and audio with expected text; never use a
  contributor's real history in CI.
- Integration: synthetic eight-hour days, migration from every released schema,
  concurrent search/write, offline sync, and provider failure injection.
- Privacy: scan the application data directory, temporary directory, logs,
  diagnostics, swap-sensitive code paths, and crash dumps for media signatures
  and seeded secrets.
- Performance: idle, active office, meeting, multi-monitor, locked, sleep/wake,
  and model-inference scenarios on low/mid/high reference systems.
- Release: unsigned builds cannot update signed installations; packages start
  at login only after consent; uninstall offers data removal and explains what
  remains.

## 8. v1 release gates

- All sources are off before consent and revocation takes effect within one
  second for event capture and five seconds for in-flight transcription.
- A permanent, OS-appropriate indicator and tray status make active collection
  discoverable; a global pause shortcut works when supported.
- No known path writes captured image, PCM, or video bytes to durable storage.
- A seeded-secret end-to-end suite shows deny-listed apps, private browser
  sessions, password fields, and private mode do not create content records.
- All durable content can be exported and deleted without an account.
- The database passes integrity checks after power-loss simulation; migrations
  are forward-only and backups are tested.
- p95 search, resource budgets, accuracy thresholds, and eight-hour soak tests
  pass on every supported OS.
- SBOM, third-party notices, Screenpipe provenance report, privacy policy,
  security contact, and signed artifacts are published.

## 9. Business model

Keep the local capture, database, search, export, and provider interfaces open.
Recommended project license: Apache-2.0 for a permissive codebase with an
explicit patent grant, plus DCO sign-off and a complete `THIRD_PARTY_NOTICES`.
Do not add a license until maintainers ratify this choice.

Sustainable paid layers can be:

- hosted transcription/summarization credits for users who do not bring a key;
- encrypted multi-device sync and managed backup;
- managed policy, support, and deployment for organizations, without exposing
  employee content to administrators;
- convenience services around signed releases and model delivery.

BYOK and local-only use should remain fully functional. Price hosted inference
from measured usage with a visible monthly ceiling. Never monetize captured
content, train on it by default, or make export/deletion a paid feature.
Do not distribute a shared vendor API key inside the app; the paid option must
use an authenticated Daytrace gateway with server-side credentials and quotas.

## 10. Open decisions for Phase 0

- Exact minimum OS versions and Linux packaging priority.
- Whether URL storage defaults to origin-only or title-only (recommend
  origin-only, with query and fragment stripped).
- Whether the first binary bundles a small speech model or downloads it after
  consent (recommend explicit download with size/hash shown).
- Whether SQLCipher-style at-rest encryption is required for v1 or the app
  relies on full-disk encryption plus OS account boundaries (recommend an
  encrypted-vault spike before committing; database key management and search
  performance must be measured).
- Whether Screenpipe reuse is worth maintaining an old fork versus clean-room
  adapters (recommend reuse only for small, isolated MIT components).
- Whether typed-text capture should exist at all. It is not required for v1.

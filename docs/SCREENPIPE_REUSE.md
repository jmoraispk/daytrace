# Screenpipe reuse audit

## Finding

The premise that current Screenpipe is MIT-licensed is no longer correct.
Screenpipe changed the repository core from MIT to the Screenpipe Commercial
License on June 10, 2026. Current `main` restricts commercial and competing use.
The license states that versions previously released under MIT remain under
MIT.

Relevant upstream points:

- Current license: [Screenpipe Commercial License](https://github.com/screenpipe/screenpipe/blob/main/LICENSE.md)
- License-change commit: [`81e412ff5`](https://github.com/screenpipe/screenpipe/commit/81e412ff5)
- Last parent verified during this audit:
  [`892199f742e46d0c5d9e8c06687b35ca7c2b6547`](https://github.com/screenpipe/screenpipe/tree/892199f742e46d0c5d9e8c06687b35ca7c2b6547)

At that parent, root `LICENSE.md` contains the MIT License for repository code
except `ee/`, which has its own enterprise license. This is an engineering
finding, not legal advice; counsel should confirm the usable boundary and
provenance before any copy enters Daytrace.

## Allowed strategies

Choose one in Phase 0:

1. **Small, pinned MIT reuse (recommended if valuable):** copy or fork isolated
   crates/files only from the verified MIT commit, exclude `ee/`, retain
   copyright/license notices, record modifications, and never merge later
   Screenpipe code without a new license review.
2. **Commercial agreement:** negotiate rights to current Screenpipe components
   and document redistribution/source obligations before implementation.
3. **Clean-room implementation:** use public OS documentation and behavior as
   references but write new adapters without copying post-change code.

Do not track Screenpipe `main`, cherry-pick an apparently unrelated new fix, or
assume a file's old history makes its current form MIT.

## Potentially useful pre-change areas to evaluate

The final MIT tree includes crates named `screenpipe-a11y`, `screenpipe-audio`,
`screenpipe-capture`, `screenpipe-core`, `screenpipe-db`, `screenpipe-engine`,
`screenpipe-events`, and `screenpipe-screen`. Evaluate them as source material,
not as an all-or-nothing dependency.

Prioritize small platform adapters or techniques that pass all of these gates:

- meaningful engineering value over a fresh implementation;
- code existed in the pinned MIT commit;
- file and transitive dependency licenses are compatible with Daytrace;
- no dependency on `ee/`, trademarks, hosted services, proprietary models, or
  post-change APIs;
- no requirement to retain raw media, which conflicts with Daytrace's design;
- tests can prove the component meets Daytrace's privacy and performance rules;
- maintainers accept ownership of an old fork and security backports.

Likely candidates for study are cross-platform device enumeration, audio
capture edge cases, screen-capture adapters, accessibility extraction, and OCR
integration. The Screenpipe database/video pipeline should not be adopted
wholesale because Daytrace intentionally has no media archive and a different
schema.

## Provenance procedure

Before importing a file:

1. record upstream repository, exact commit, path, blob hash, copyright, and
   license in `THIRD_PARTY_NOTICES` and a machine-readable provenance file;
2. inspect `git log --follow` for that path and confirm it predates the license
   change;
3. run a dependency license scan and manually inspect build scripts, model
   weights, native libraries, and bundled assets;
4. copy into an isolated commit labeled `third-party import`; do not mix it with
   refactoring;
5. preserve notices in source and distributions;
6. list Daytrace modifications in subsequent commits;
7. configure automation to reject Screenpipe commits newer than the approved
   SHA unless legal review updates the allow list.

## Architectural lessons, independent of copying

Current Screenpipe publicly documents an event-driven capture approach,
accessibility-first text with OCR fallback, local SQLite/FTS search, and a Tauri
UI. Those validate the broad direction, but Daytrace should diverge in several
ways:

- no JPEG/MP4/audio archive;
- bounded in-memory media and backpressure that drops media rather than spills;
- source-specific consent and retention;
- keyboard activity instead of raw typed content in v1;
- no general localhost SQL/API surface;
- deterministic, mergeable text export instead of database/media sync.

Upstream architecture and testing references:

- [Screenpipe repository](https://github.com/screenpipe/screenpipe)
- [Screenpipe event-driven capture source](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-engine/src/event_driven_capture.rs)
- [Screenpipe testing checklist](https://github.com/screenpipe/screenpipe/blob/main/TESTING.md)

Links to current files are for architectural research only and do not grant a
license to copy their current content.

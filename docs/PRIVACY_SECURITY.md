# Privacy and security model

Daytrace processes some of the most sensitive data on a computer. Privacy is an
architecture constraint, not an onboarding paragraph.

## Invariants

1. Every source is off by default and independently revocable.
2. The app is never stealthy: tray state, OS indicators, and pause controls are
   truthful and readily available.
3. Captured images, PCM/audio, and video are never intentionally written to
   Daytrace durable storage, logs, crash reports, exports, or model requests.
4. Network egress is denied by design except for a user-configured provider,
   GitHub sync, signed updates, or separately consented diagnostics.
5. Secrets live in OS credential storage, not settings, SQLite, logs, CLI
   arguments, environment exports, or Git.
6. Deny rules and private mode are enforced before capture wherever the OS
   provides enough metadata, then rechecked before persistence and egress.
7. The user can inspect, edit, export, and delete all durable content without an
   account or subscription.

## Consent model

Onboarding explains and requests one capability at a time. Enabling a toggle is
not equivalent to OS permission: Daytrace records requested, OS-granted, active,
paused, denied, and unavailable as distinct states.

Each disclosure shows:

- what signal is observed;
- what text is kept;
- what is discarded;
- when it runs;
- whether data can leave the device;
- how to pause, filter, and delete it.

Materially broader collection (typed text, URLs, cloud processing, diagnostics)
requires a new versioned consent. Updating the app must not silently enable it.

## Keyboard policy

Keyboard access is uniquely dangerous because it can expose passwords, private
messages, financial data, recovery phrases, and authentication codes.

The v1 “keyboard activity” option stores only per-minute aggregate counts,
active/idle transitions, and an allow-list of non-text shortcuts such as copy or
save when useful for activity segmentation. It discards scan codes and character
values immediately. The UI must call this “keyboard activity,” not imply typed
text is retained.

If typed-text mode is ever built, it must be an advanced feature with:

- separate consent and a persistent visual indicator;
- default-deny behavior in password/secure-input fields and private browsing;
- per-app and per-window allow lists (not only deny lists);
- no clipboard capture by implication;
- bounded phrase buffers that are redacted before persistence;
- an emergency pause shortcut handled before any other processing;
- dedicated external security review and store-policy review.

Unsupported password detection means typed-text capture pauses; it never means
“capture anyway.” Remote activation and organizational coercion are non-goals.

## Ephemeral media handling

Screen frames and microphone samples use preallocated, bounded memory pools.
Media types do not implement serialization or debug formatting. Only the
extractor can consume them; storage and sync APIs accept text-domain types.

On completion, cancellation, timeout, panic boundary, permission revocation, or
queue eviction:

- release native GPU/audio handles;
- zero CPU-owned buffers where the platform permits;
- remove references promptly;
- never spill queues to disk;
- emit only a content-free health/gap event.

Zeroing memory cannot guarantee removal from every OS/driver copy or swap. The
product language must say “Daytrace does not intentionally persist raw media,”
not promise physically impossible erasure. Recommend full-disk encryption and
disable content-bearing crash dumps.

## Threats and controls

| Threat | Primary controls |
|---|---|
| Accidental capture of a secret | pre-capture app/window rules, password/secure-input pause, private mode, local redaction, rapid delete |
| Malicious webpage prompt injection | treat captured text as untrusted data, fixed delimiters, typed output schema, no model tools/database access |
| Stolen API/GitHub token | OS vault, least privilege, PKCE, rotation/revoke UI, log redaction |
| Compromised renderer | Tauri capability allow list, strict CSP, no remote UI content, no general shell/fs/network commands, Rust-side validation |
| Local malware or another account | OS account isolation, optional encrypted vault, signed builds; acknowledge same-user malware is out of scope |
| Cloud provider retention | explicit provider disclosure, local default, minimization, per-request preview/log, documented provider terms |
| Git history retaining deletions | summaries-only default, optional client encryption, tombstones, clear warning that remote history may persist |
| Supply-chain compromise | locked dependencies, review bots, SBOM, provenance, signed artifacts/updates, reproducible-build work |
| App silently stops recording | health state and tray warning; content-free gap records; no fabricated timeline |
| App records while believed paused | cancellation deadline tests, monotonic state machine, OS indicator checks, prominent state transitions |

## Data at rest

Baseline v1 relies on OS account permissions and recommends full-disk
encryption. Evaluate an encrypted SQLite build during Phase 0. If shipped, the
database key must be generated locally, stored in the OS vault, recoverable only
through an explicit user-controlled recovery flow, and never required by a
Daytrace service. Search/performance, crash recovery, and Linux secret-service
availability must be tested before claiming encrypted-at-rest support.

Backups inherit the same sensitivity. Automatic plaintext backups outside the
application data directory are forbidden.

## Network and AI boundaries

- Local deterministic summaries are always available.
- Installed local runtimes receive loopback-only requests after endpoint
  validation; Daytrace does not assume every localhost process is trustworthy.
- BYOK providers receive the minimum selected text range. The UI shows provider,
  model, estimated size/cost, and data categories before first use.
- The future hosted gateway authenticates users, enforces quotas, avoids
  content-bearing logs, and documents retention. It should proxy requests
  without building a second journal.
- Captured text is never used for training unless a future, distinct feature
  obtains specific opt-in consent; this is outside v1.

## Logging and diagnostics

Use structured event codes and metrics such as duration, queue depth, model
name, byte counts, and error class. Do not log observation text, transcripts,
window titles, URLs, paths, usernames, device names, prompt bodies, provider
responses, or tokens. A support bundle is locally previewable and generated
only on request.

Telemetry is off by default in the initial open-source release. If introduced,
crash reporting and product analytics are separate opt-ins with separate
payload previews and endpoints.

## Security operations

- Publish `SECURITY.md`, supported versions, and a private disclosure channel.
- Run automated dependency/license/secret scanning and manual review of every
  new OS entitlement or Tauri capability.
- Rotate signing/update keys through a documented offline process and practice
  revocation/rollback.
- Maintain a data-flow diagram and privacy regression suite as release-blocking
  artifacts.
- Obtain legal review for recording/consent laws and app-store policies in
  target markets. Daytrace should encourage visible individual use, not provide
  legal conclusions in-product.

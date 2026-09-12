# Activity Episode Compaction and Large-Day AI Design

**Date:** 2026-09-12  
**Status:** Approved direction; implementation pending  
**Target release:** DayTrace 0.3.0

## Problem

DayTrace 0.2.0 sanitizes, fuses, and sessionizes ActivityWatch data before an
optional AI summary. On a representative 7h 12m day it produced 437 sessions;
334 (76%) were shorter than one minute. A generic `ChatGPT` label appeared 124
times, while the complete report contained only 94 distinct labels.

This is a useful audit trail but a poor journal and a wasteful model input. The
provider payload repeats structured timestamps, applications, titles, contexts,
and evidence for every fragmented session. It can therefore exceed DayTrace's
100,000-character provider-input ceiling even when the rendered Markdown is
only about 25,000 characters. DayTrace 0.2.0 then emits a deterministic fallback
with a generic warning that does not distinguish request size, provider failure,
or invalid model output.

The fallback also demonstrated that title sanitization is incomplete. A window
title shaped like an OAuth URL retained query parameters, and communication
titles retained personal names. Those fields should not be sent to a cloud
model merely because they survived the general sanitizer.

## Goals

1. Convert fragmented sessions into deterministic, project-neutral activity
   episodes before any AI request.
2. Make the default deterministic output useful as a compact journal handoff.
3. Preserve exact measured active and focused duration; compaction must never
   invent, duplicate, or discard measured time.
4. Preserve enough evidence for an AI model to infer broad workstreams, topics,
   and apparent achievements without receiving every foreground transition.
5. Minimize cloud-bound titles, URLs, filenames, and communication metadata
   beyond the local-output sanitization baseline.
6. Support unusually large days through bounded, hierarchical model calls after
   deterministic compaction.
7. Keep the detailed sanitized timeline available for audit and debugging.
8. Emit privacy-safe, actionable failure categories.
9. Keep canonical project definitions and final project mapping in Obsidian.

## Non-goals

- DayTrace will not read the Obsidian vault or own canonical project names.
- Deterministic compaction will not use an AI model or claim semantic certainty.
- DayTrace will not retain raw ActivityWatch events or new durable private data.
- Compaction will not infer message contents, browser page contents, or work that
  is not evidenced by the sanitized trace.
- This release will not add a GUI, background capture, or hosted inference.

## Pipeline

```text
ActivityWatch
  -> normalize and sanitize observations
  -> fuse watcher overlap into foreground slices
  -> reconstruct fine-grained sessions
  -> compact sessions into activity episodes
  -> minimize the cloud evidence view
  -> one AI call, or bounded chunk calls plus one merge call
  -> validated workstream digest
  -> later Obsidian project mapping
```

Fine-grained sessions remain the lossless sanitized audit representation.
Episodes become the normal human-facing and provider-facing representation.

## Data model

Add an immutable `ActivityEpisode` with:

- stable `episode_id` within the day;
- start and end timestamps;
- exact summed active seconds and optional focused seconds;
- ordered source session IDs;
- a deterministic display label;
- strong anchors such as repository, editor project, document, specific browser
  path/domain, or specific conversation/topic title;
- aggregated application names and normalized distinct context labels;
- transition count and source-session count;
- propagated outcome signals and evidence IDs.

Add an `EpisodeBundle` containing the day, timezone, exact daily focused time,
ordered episodes, fine-grained sessions, and aggregate diagnostics. The sessions
remain available to `--raw` and local callers but are excluded from the normal
cloud payload.

## Anchor classification

Every fine-grained session receives zero or more normalized anchors.

Strong anchors identify a plausible work object:

- repository or merge-request path;
- editor project;
- specific filename or document title;
- specific browser domain/path;
- specific AI conversation title;
- meeting or communication topic when a non-personal topic is available.

Weak context identifies a tool or transition but not a work object:

- generic ChatGPT or other assistant home view;
- terminal or PowerShell;
- Explorer/Finder;
- new tab, inbox, Slack, Outlook, or unknown activity;
- installer shells and operating-system surfaces without a specific artifact.

Anchor normalization is deterministic: case-fold for comparison, strip known
application suffixes, collapse whitespace, use repository/path basenames where
appropriate, and retain a sanitized display form separately.

## Episode compaction

Compaction processes sessions chronologically and applies these rules:

1. A strong anchor begins or continues an episode with the same anchor set.
2. Episodes with a shared strong anchor may bridge weak sessions and short
   interruptions when the elapsed wall-clock gap is at most five minutes.
3. A weak session bounded on both sides by compatible strong anchors joins that
   episode.
4. A weak session adjacent to only one strong episode may join it when it is at
   most two minutes away and no competing strong anchor exists.
5. Weak activity between incompatible strong anchors is not guessed into either
   project; it remains a separate general/communication episode.
6. A strong-anchor change always prevents bridging unless the two sessions share
   another strong anchor, such as the same repository.
7. Repeated visits inside an episode are aggregated into distinct labels plus
   counts; they are not emitted as repeated rows.
8. Outcome signals are unioned without duplication and retain their source
   evidence.
9. Episode active duration is the exact sum of member-session active duration.
   Focused duration follows the same rule when it is available.

The five-minute and two-minute thresholds are named constants with focused unit
tests. They are not user-facing configuration in this release.

Compaction must be idempotent: compacting an episode-derived session sequence a
second time must not further change episode membership or duration.

## Default and detailed output

The default deterministic Markdown shows compact episodes rather than every
fine-grained session. A typical entry is:

```text
07:05-07:22 · 16m · PerfLife repository setup
  Anchors: jmoraispk/perflife; PerfLife health-data planning
  Tools: Claude, ChatGPT, GitHub
  Activity transitions: 20
  Evidence: named repository appeared
```

The label must remain deterministic and evidence-based; terms such as
"repository setup" may be used only when a matching outcome signal exists.
Otherwise the most specific anchor becomes the label.

`--details` adds minimized contexts, source-session IDs, and duration breakdowns
to episodes. `--raw` preserves the current chronological fine-grained session
and slice view. `--diagnostics` remains content-free. JSON output receives a new
versioned episode schema while retaining explicit provenance for AI digests.

## Cloud evidence minimization

The provider request is derived from episodes, never directly from raw events or
the complete fine-grained session bundle.

Before serialization:

- deduplicate applications, anchors, labels, and outcome signals;
- replace repeated transitions with counts;
- omit source event IDs and source bucket IDs;
- omit fine-grained timestamps inside an episode;
- strip query strings and fragments from any URL-shaped value, including window
  titles rather than only browser URL fields;
- remove email addresses, OAuth parameters, tokens, and credential-shaped text;
- omit personal names from communication titles in the cloud view; retain only
  the application/team surface and a non-personal channel or meeting topic when
  available;
- reduce local filesystem paths to safe basenames;
- apply the generated-text secret scanner to every final model-produced string.

The local raw view may retain sanitized participant names because it never
leaves the machine, but the pre-send disclosure must list communication metadata
when any survives minimization.

## Provider request and large-day strategy

Retain a 100,000-character hard ceiling per provider call. Do not solve normal
fragmentation by silently increasing it.

If the complete compact episode request fits, use one model call.

If it does not fit:

1. Partition episodes chronologically at episode boundaries into requests
   targeting at most 80,000 serialized characters each.
2. Never split one episode. If a single minimized episode exceeds the hard
   ceiling, fail with an explicit safe diagnostic.
3. Summarize each chunk with the same evidence-citation contract. Chunk results
   cite episode IDs, not source-session IDs.
4. Send a final merge request containing only provisional workstreams, topics,
   outcomes, confidence, and episode IDs. The merge request must also remain
   below the hard ceiling.
5. Validate that every episode ID appears exactly once in the final digest and
   that every topic/outcome cites an allocated episode.

Chunk boundaries do not become workstream boundaries. The merge pass may combine
compatible provisional workstreams but may not create new evidence or stronger
outcome claims than the chunk results support.

The consent disclosure occurs once before any call and reports:

- episode count;
- number of planned summarization chunks and whether a merge call is required;
- total serialized input characters across the initial calls;
- provider and model;
- data categories included.

The API key is requested only after confirmation and remains memory-only.

## Error behavior

All errors remain free of captured content and secrets, but the CLI distinguishes:

- sanitized episode request exceeds the per-call limit;
- one episode is too large to chunk safely;
- provider authentication/access/billing failure;
- provider rate-limit or transient service failure;
- network failure;
- invalid or incomplete structured model response;
- invalid final episode allocation.

When an explicitly requested AI operation fails at any stage, DayTrace atomically
writes the compact deterministic episode fallback and exits with status 2. It
does not expose provider response bodies, request payloads, titles, or key data.

## Validation and privacy invariants

- Sum of episode active seconds equals sum of source-session active seconds.
- Focused seconds are preserved exactly when available.
- Every source session belongs to exactly one episode.
- Every episode belongs to exactly one final workstream or the unassigned set.
- Model output cannot cite unknown episode IDs.
- Outcome strength cannot be increased during the merge pass.
- Cloud payloads contain no raw query strings, fragments, email addresses,
  credential-shaped values, personal communication titles, source event IDs, or
  source bucket IDs.
- Deterministic fallback requires no model and no API key.

## Test strategy

Unit tests cover anchor normalization, compatible and incompatible bridging,
weak-session attachment, aggregation, idempotence, duration conservation, cloud
minimization, request partitioning, and final allocation validation.

A synthetic high-fragmentation fixture mirrors the observed shape without using
private captured text:

- at least 437 fine-grained sessions;
- at least 75% shorter than one minute;
- repeated generic assistant, browser-tab, terminal, and file-manager labels;
- several interleaved repositories, documents, meetings, and personal workflows;
- bounded outcome signals.

For that fixture, acceptance requires:

- no more than 80 compact episodes;
- at least 70% fewer provider-facing activity items;
- a single minimized provider request below 100,000 characters;
- exact duration and allocation conservation;
- no incompatible-anchor merge;
- no forbidden private field in Markdown, JSON, provider requests, or errors.

Integration tests use a recording provider to verify single-call and chunked
flows, disclosure-before-key ordering, merge constraints, deterministic fallback,
and atomic output. Golden tests cover compact Markdown and versioned JSON.

The full suite runs on Linux, macOS, and Windows for Python 3.11 through 3.14.

## Compatibility and release

This changes the default deterministic representation, the provider request
schema, and JSON output, so it is a minor release: `0.3.0`.

- Markdown consumers should treat headings and prose as presentation, not a
  stable machine interface.
- The new JSON schema gets a new identifier; the 0.2 schema is not silently
  reused with different semantics.
- Existing `activitywatch`, `--summary`, `--provider`, `--model`, `--details`,
  `--raw`, `--diagnostics`, `--format`, and `--yes` flags remain accepted.
- README examples will describe compact episodes, raw audit output, chunked AI
  calls, safe failure categories, and Obsidian handoff.

Completion includes version bumping, full tests, wheel/sdist validation, pushing
`main`, publishing to PyPI, pushing `v0.3.0`, and verifying a clean public
`uvx daytrace@latest` installation.


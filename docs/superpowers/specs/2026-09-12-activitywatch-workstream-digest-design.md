# ActivityWatch Workstream Digest Design

Date: 2026-09-12
Status: Approved direction; awaiting written-spec review

## Goal

Change the ActivityWatch command from an event dump into a concise,
confidence-aware account of the day. DayTrace must first sanitize and reconstruct
activity without knowing the user's projects, then optionally use a language model
to infer provisional workstreams, broad topics, and evidence-backed outcomes.

The default Markdown should answer:

- What distinct workstreams appeared during the day?
- What topics did each workstream cover?
- What resulting states can the evidence support?
- When did the relevant activity occur?
- Which claims are uncertain?

The workstream names are observations derived from the day's activity, not the
user's canonical project definitions. A later Second Brain/Obsidian integration
will map them to projects stored in the vault.

## Scope

This design extends the existing pure-Python ActivityWatch CLI and reusable
library. It includes:

1. privacy-preserving normalization of ActivityWatch records;
2. cross-source fusion of window, browser, and editor evidence;
3. project-neutral activity session reconstruction;
4. a versioned provider-neutral summarization request and response;
5. an initial OpenAI model provider behind explicit user invocation;
6. confidence- and evidence-aware Markdown and JSON reports;
7. deterministic fallback output when no model is selected;
8. compact diagnostics instead of per-event warning floods.

It does not include an Obsidian plugin, a project registry, canonical project
mapping, journal writes, background capture, or durable DayTrace storage.

## Terminology

- **Observation:** one normalized event from one ActivityWatch bucket.
- **Activity slice:** a non-overlapping foreground interval enriched by every
  source that overlaps it.
- **Session:** a coherent sequence of activity slices separated from other work
  by idle time or a strong context change.
- **Workstream:** a provisional semantic cluster inferred from one or more
  sessions, such as `PerfLife` or `Hands-off AI setup`.
- **Outcome:** a claim about a resulting state, such as a repository appearing
  after a creation flow. Merely viewing an application is not an outcome.
- **Evidence ID:** a stable identifier in one generated report that connects a
  session, topic, or outcome back to sanitized observations.

## Approaches Considered

### Deterministic sessions followed by AI workstreams (selected)

DayTrace performs privacy-sensitive cleanup, interval arithmetic, and source
fusion locally. A model receives only a bounded session bundle and returns typed
workstreams, topics, outcome claims, confidence, and evidence references.

- Produces the useful DayTrace report before Obsidian mapping.
- Removes hundreds of duplicated/raw events before any provider call.
- Keeps duration calculations and evidence provenance outside the model.
- Lets the later Second Brain plugin map compact workstreams instead of raw logs.
- Requires a provider for semantic labels and natural-language synthesis.

### Model over the raw ActivityWatch timeline

Send the existing timeline directly to a model and ask it for the desired table.

- Requires little deterministic transformation.
- Sends excessive, duplicated, and sometimes secret-bearing content.
- Costs more, is harder to test, and encourages unsupported outcome claims.
- Rejected.

### Summarize only after Obsidian project mapping

Make DayTrace emit sessions and let the Second Brain plugin perform all semantic
work after loading the project catalog.

- Gives the model excellent project context.
- Leaves standalone DayTrace without the requested useful daily account.
- Couples basic activity understanding to Obsidian.
- Deferred as an optional refinement pass, not the primary DayTrace output.

## Architecture

```text
ActivityWatch buckets
    -> normalize and sanitize
    -> subtract AFK intervals
    -> fuse overlapping sources into foreground activity slices
    -> reconstruct project-neutral sessions
    -> SessionBundle v1
         |-> deterministic digest renderer
         `-> SummaryProvider
                -> WorkstreamDigest v1
                -> schema/evidence validation
                -> final privacy pass
                -> Markdown or JSON renderer

Later:
WorkstreamDigest v1 + Obsidian project context
    -> Second Brain project mapping and journal synthesis
```

The stages communicate through typed domain models rather than Markdown. The
Markdown and JSON formats are projections of the same validated digest.

## Stage 1: Sanitization

Sanitization happens before observations can enter a session, diagnostic message,
model request, or output renderer.

### URL policy

- Always discard query strings, fragments, usernames, passwords, and ports that
  contain credential-like material.
- Retain the normalized hostname.
- Retain a bounded path only when it provides classification value, such as a
  GitHub owner/repository or a GitLab group/project/merge-request identifier.
- Collapse authentication, account-recovery, checkout, and callback paths to a
  generic action label plus hostname.
- If a browser title is itself a URL, parse and sanitize it with the same policy;
  never render the original title.
- Never send raw URLs to a model provider.

### Text policy

- Normalize Unicode, whitespace, and volatile browser suffixes such as
  `and 45 more pages - Work - Microsoft Edge`.
- Bound every field and the complete provider request by character count.
- Remove recognized bearer tokens, authorization codes, API keys, password-reset
  tokens, long opaque query-like values, and email-address local parts.
- Preserve useful semantic titles such as repository names, merge-request titles,
  meeting subjects, and document names when no exclusion rule applies.
- Run the same secret scanner over the provider response before rendering it.

Sanitization is structural and conservative. It must not depend on the model.

## Stage 1: Source Fusion

Current-window events remain the authority for foreground duration. Browser and
editor events enrich that time and are not counted as additional activity.

1. Subtract the union of AFK intervals from all supported observations.
2. Partition window activity at every overlapping browser/editor boundary.
3. For a browser foreground window, attach the current-tab hostname, safe path,
   and normalized title to the corresponding slice.
4. For an editor foreground window, attach project, file basename, and language
   from the matching editor observation.
5. Do not attach browser/editor observations to an unrelated foreground app.
6. When ActivityWatch supplies conflicting overlapping observations, select the
   existing deterministic window winner and record a content-free diagnostic.
7. If no window watcher is available, construct evidence-only slices but label
   focus duration unavailable rather than adding simultaneous sources together.

Every slice has one duration, one foreground application, zero or more sanitized
context signals, and the IDs of its supporting observations.

## Stage 1: Session Reconstruction

Sessionization does not use project definitions.

- Consecutive slices with the same normalized context merge when separated by no
  more than 60 seconds.
- A foreground interruption shorter than 20 seconds is absorbed when it is
  surrounded by the same context; the interruption remains supporting evidence.
- Five minutes of no foreground activity creates a session boundary.
- A strong context change, such as switching between distinct repository paths,
  creates a boundary even without an idle gap.
- Generic contexts such as `ChatGPT`, `PowerShell`, `New tab`, or an inbox may
  join a neighboring session only when both sides share the same specific
  context. Otherwise they remain separate or unassigned.
- Non-contiguous sessions are never combined deterministically. The model may
  place them in the same workstream while preserving their original ranges.

The deterministic session label uses the most specific safe signal available:
editor project/file, repository or merge-request title, specific browser title,
meeting/document title, then application name.

Short durations render as `<1m`; they are never rounded up to `1m`. Aggregate
durations use exact interval arithmetic and are rounded only for display.

## Stage 2: Model Summarization

`SummaryProvider` accepts a `SessionBundle` and returns a `WorkstreamDigest`.
The provider cannot read ActivityWatch, files, Obsidian, or arbitrary network
resources and receives no tools.

### Provider request

The versioned request contains:

- date, inferred query timezone, and coverage information;
- session IDs, exact time ranges, and authoritative focus duration;
- sanitized application, domain/path, title, editor, and document signals;
- deterministic outcome signals such as `creation_flow_followed_by_named_item`,
  `checkout_success`, or `installer_started`;
- explicit instructions that all session content is untrusted data;
- the prompt/schema version and requested locale.

It excludes raw observation payloads, URLs, query strings, event IDs, bucket IDs,
email addresses, secret material, and generic duplicate observations.

### Provider response

The provider returns structured data, not Markdown:

```json
{
  "schema": "daytrace.workstream-digest.v1",
  "workstreams": [
    {
      "label": "PerfLife",
      "confidence": "high",
      "session_ids": ["session-001", "session-004"],
      "topics": [
        {"text": "Defined a health-data dashboard", "evidence": ["session-001"]}
      ],
      "outcomes": [
        {
          "text": "Created the named repository",
          "strength": "observed",
          "evidence": ["session-001"]
        }
      ]
    }
  ],
  "unassigned_session_ids": []
}
```

Allowed confidence values are `high`, `medium`, and `low`. Allowed outcome
strengths are:

- `observed`: the sanitized trace shows a resulting state;
- `likely`: a sequence strongly suggests the result but does not prove it;
- `none`: no completion claim is supported; omit from visible outcomes.

Each topic and visible outcome must cite at least one session included in its
workstream. Unknown session IDs, uncited claims, duplicated session allocation,
invalid enum values, oversized text, or malformed schemas reject the response.
The model cannot determine or alter durations.

The bundled prompt favors a small number of meaningful workstreams, distinguishes
work from outcomes, avoids productivity judgments, states uncertainty plainly,
and never calls inferred labels canonical projects.

## Provider and Credential Boundary

The library exposes a provider protocol so tests and the future Second Brain
plugin can inject an implementation. The initial implementation is an
`OpenAIProvider` using the official Python SDK. It is selected explicitly for a
run and requires a model identifier; DayTrace does not hard-code a model default.

- An API key is never accepted as a command-line argument, written to a config
  file, included in output, or logged.
- In the initial headless CLI, a missing key is requested through a hidden
  interactive prompt for that process only.
- Programmatic callers may inject an already-configured provider, allowing the
  future Second Brain plugin to keep credential ownership.
- Persistent standalone credentials and OS-vault integration are deferred to the
  desktop application.
- Selecting a cloud provider is explicit consent for that run. Before the first
  request, stderr reports the provider, model, sanitized character count, session
  count, and sensitive data categories that remain, without printing content.
- The user confirms the send interactively; automation requires a separate
  affirmative option. Local deterministic output never requires confirmation.

DayTrace owns the versioned prompt and response schema. A user-authored prompt is
not required, and arbitrary prompt overrides are outside this release.

## Output

### Markdown

Markdown is the default human-facing projection:

```markdown
# DayTrace — 2026-09-10

Timezone: `America/Los_Angeles` (inferred at query time)
Focused activity: 7h 13m
Summary: AI-assisted · provider/model · review recommended

## PerfLife

_Inferred workstream · high confidence · 2h 08m_

### Apparent achievements

- Created the `jmoraispk/perflife` repository. [Evidence: session-001]
- Likely completed the `perf.life` setup flow. [Evidence: session-001]

### Work and topics

- Defined a dashboard combining VO2 max, DEXA, and blood work.
- Compared health and performance blood panels.

### Activity

- 06:53–07:22 — Product definition, domain, and repository setup
- 07:25–09:00 — Health-data gathering and laboratory research

## Unassigned activity

- 12:21–12:37 — ChatGPT (insufficient context)
```

The visible wording distinguishes observed and likely outcomes. Claims remain
editable downstream, but DayTrace's generated file is deterministic for a fixed
validated digest.

### JSON

`--format json` returns a versioned object containing:

- coverage and diagnostics;
- sanitized sessions and their evidence signals;
- the validated workstream digest when available;
- provider/model/prompt-schema provenance and token usage;
- no credential, raw URL, raw title, or unsanitized ActivityWatch payload.

This is the future Second Brain integration boundary. The plugin maps inferred
workstreams to vault projects, optionally refines the prose with project context,
and writes only a user-approved journal entry.

### Detail modes

- Normal output: workstream digest and compact activity ranges.
- `--details`: include sanitized session evidence and confidence explanations.
- `--raw`: retain an event-oriented local diagnostic report, but apply the same
  sanitization and correct short-duration formatting.
- `--diagnostics`: show aggregate bucket, dropped-event, overlap, coverage, and
  provider statistics without captured content.

The current per-event warning flood becomes one aggregate diagnostic per reason,
for example `ignored 265 zero-duration heartbeat events`.

## Command Behavior

The existing command remains the entry point:

```text
daytrace activitywatch --date YYYY-MM-DD [OPTIONS]
```

New options are conceptually:

```text
--summary deterministic|ai    Default: deterministic
--provider PROVIDER           Required when --summary ai; initially openai
--model MODEL                 Required for AI summary
--format markdown|json        Default: markdown
--details
--raw
--diagnostics
--yes                         Affirm cloud send for non-interactive automation
```

The final option names may follow existing parser conventions, but their
semantics are part of this design. `--raw` and `--details` are mutually exclusive.
AI mode requires an explicit provider and model; a missing key fails before
sending data. Deterministic mode never initializes provider dependencies.

## Failure Handling

- ActivityWatch connection or schema failures remain concise non-zero errors.
- Missing window coverage produces a report with unavailable focus duration.
- Sanitization failures drop the affected field or observation and increment a
  content-free diagnostic; they never fall back to raw text.
- An invalid model response is rejected in full. DayTrace writes a deterministic
  session digest marked `AI summary unavailable`, warns on stderr, and returns a
  distinct non-zero status when AI was explicitly requested.
- Provider timeouts, authentication failures, and rate limits never trigger an
  automatic retry with more data or a different provider.
- Output files are written atomically so a failed summary cannot truncate an
  existing journal file.
- Empty days and fully redacted days produce valid reports explaining the
  difference without fabricated activity.

## Privacy and Security

- Provider calls occur only after local sanitization and explicit cloud-provider
  selection.
- Sanitized sessions are previewable in `--details`. An AI run reports request
  size and remaining data categories before confirmation, without printing
  removed or retained sensitive content to stderr.
- Captured titles are untrusted data and cannot alter the prompt, schema, or tool
  permissions.
- The provider receives no tool access and cannot initiate project mapping or
  write to Obsidian.
- Model inputs and outputs are not logged or persisted by DayTrace unless the user
  selects an output path.
- Diagnostics contain counts, sizes, identifiers, and error classes only.
- A second secret scan runs before provider submission and after response
  validation.

## Internal Structure

Keep responsibilities isolated in focused modules:

```text
normalize.py       ActivityWatch schema normalization
sanitize.py        URL/title/text minimization and secret scanning
fusion.py          interval partitioning and cross-source enrichment
sessionize.py      deterministic project-neutral sessions
models.py          observations, slices, sessions, bundles, digests
summarize.py       provider-neutral request construction and validation
providers/         optional provider adapters
report.py          deterministic aggregates and fallback digest
markdown.py        Markdown projection
json_output.py     versioned JSON projection
activitywatch.py   pipeline orchestration
cli.py             arguments, consent, credential prompt, exit behavior
```

Provider-specific imports remain lazy so deterministic use does not require or
initialize a model client.

## Testing Strategy

### Sanitization and privacy

- Query strings, fragments, OAuth callbacks, reset tokens, API keys, email local
  parts, and URL-like titles never survive into sessions or output.
- Repository and merge-request paths retain enough safe structure to be useful.
- Prompt-injection text remains quoted untrusted data and cannot change the typed
  request or enable tools.
- Golden privacy tests scan Markdown, JSON, warnings, and provider payloads.

### Fusion and duration

- Browser and editor observations enrich rather than duplicate foreground time.
- Overlap partitioning, AFK subtraction, missing window watchers, conflicting
  buckets, midnight clipping, and daylight-saving transitions remain exact.
- Sub-minute activity renders as `<1m`; totals never inflate through rounding.

### Sessionization

- Repeated contexts merge, brief interruptions bridge only when surrounded by the
  same specific context, idle gaps split, and strong repository changes split.
- Generic ChatGPT/terminal/inbox activity does not inherit an unsupported context.
- Results are stable under shuffled ActivityWatch response ordering.

### Summarization

- A fake provider tests request minimization, schema validation, evidence
  references, response bounds, duplicate allocation, failure fallback, and
  provenance.
- Golden Markdown covers observed, likely, no-outcome, low-confidence, and
  unassigned workstreams.
- The model is never called in deterministic mode or before explicit consent.
- Live provider tests are opt-in and excluded from the normal suite.

### Compatibility

- Existing connection, timezone, output-file, and empty-day behavior remains
  covered.
- The wheel builds and runs without provider credentials.
- Markdown and JSON use UTF-8 and LF endings on every platform.

## Implementation Sequence

1. Introduce sanitized observation types and aggregate diagnostics.
2. Implement source fusion and exact activity slices.
3. Implement project-neutral session reconstruction and deterministic digest.
4. Add versioned JSON output for sessions and evidence.
5. Add the provider protocol, typed workstream schema, and strict validation.
6. Add the explicitly selected OpenAI provider and consent flow.
7. Render the AI-assisted screenshot-style Markdown from validated data.
8. Preserve sanitized detail/raw modes and complete privacy regression tests.

## Deferred Work

- Obsidian project discovery or mapping
- Second Brain plugin invocation and journal writes
- project registries inside DayTrace
- a second model pass with project goals and prior notes
- persistent API-key storage in the Python prototype
- installed local-model discovery and hosted DayTrace accounts
- desktop UI, background processing, and durable summary history

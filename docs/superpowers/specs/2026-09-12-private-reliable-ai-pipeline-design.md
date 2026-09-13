# Private and Reliable AI Pipeline Design

Date: 2026-09-12
Status: Approved direction; awaiting written-spec review

## Context

DayTrace 0.3.1 can sanitize ActivityWatch events, fuse them into foreground
activity, compact sessions into episodes, and ask an OpenAI model for an
evidence-backed workstream digest. A representative 7h 12m trace exposed three
separate problems at the boundary between those stages:

1. A credential-like query value in a title containing a loopback or private-IP
   URL survived both local and cloud sanitization.
2. The provider's strict JSON Schema accepts some allocations and evidence
   arrays that DayTrace's semantic validator rejects. The CLI then discards the
   provider response and reports only a generic warning.
3. Fifty-four nominally compact episodes still produced 66,663 characters of
   provider input. They contained 593 anchors, including 445 titles, and some
   episodes mixed several unrelated repositories through transitive anchor
   chaining.

The captured trace is useful as a local investigative artifact, but private
captured text must not become a committed fixture. Regression tests use
synthetic values that reproduce the relevant shapes.

## Goals

- Prevent URL credentials and query data from reaching local output, support
  artifacts, or model providers.
- Make provider-side structured output agree with DayTrace's local validation
  contract wherever OpenAI's supported JSON Schema subset permits it.
- Preserve enough content-free failure information to diagnose the remaining
  semantic constraints without retaining private provider content.
- Stop unrelated sessions from becoming one indivisible model input unit.
- Reduce provider input by ranking and bounding evidence rather than merely
  accepting any request below the hard character ceiling.
- Preserve exact measured duration and one-to-one episode allocation.
- Keep project definitions and canonical mapping outside DayTrace.

## Non-goals

- Storing API keys, provider request bodies, provider response bodies, raw
  ActivityWatch events, or unredacted support logs.
- Reading an Obsidian vault or assigning canonical project identifiers.
- Weakening evidence validation to accept an internally inconsistent model
  response.
- Treating a successful HTTP response as a successful summary.
- Committing the supplied personal trace to the repository.

## Approaches Considered

### Two releases with a sanitized recapture between them (selected)

Release 0.3.2 fixes the privacy boundary, disables provider persistence, aligns
the response schema as far as possible, and adds content-free diagnostics. The
user then captures a sanitized session-level JSON artifact with 0.3.2. Release
0.4.0 uses that artifact locally to verify a conservative episode algorithm and
bounded evidence selection.

This sequence handles the credential exposure immediately and supplies the
session-level evidence needed to change compaction scientifically.

### One combined release from the episode-only artifact

The current artifact can reproduce the provider request but cannot reconstruct
the sessions and slices that were merged into each episode. Changing compaction
from it would optimize only the observed output and could introduce new duration
or grouping errors. Rejected.

### Provider retry without changing local preparation

A retry could occasionally repair allocation mistakes, but it would resend an
overlarge, mixed input and could still produce structurally valid nonsense.
Rejected as a symptom-only fix.

## Release 0.3.2: Privacy and Diagnostic Boundary

### URL sanitization

All URL-shaped text uses one structural sanitizer before it becomes a title,
anchor, label, rendered value, or provider field. The sanitizer recognizes:

- ordinary DNS hostnames;
- IPv4 and bracketed IPv6 hosts;
- `localhost`, with or without a port;
- URLs with or without a scheme.

For recognized URLs it removes the username, password, port, query, and
fragment. It returns only the normalized hostname or another explicitly safe
classification field. Secret scanning remains a second layer for
credential-shaped text that is not a complete URL. Generic parameter names such
as `key`, `secret`, and `access_token` are covered when followed by a long opaque
value.

The same sanitizer is applied locally and again when constructing cloud-bound
fields. A provider request containing a recognized URL query or fragment, a URL
userinfo component, or a recognized credential assignment fails closed before
network egress. Natural-language punctuation is not treated as a URL query.

### Provider retention

Every OpenAI Responses API request sets `store=False`. DayTrace does not use
provider retention as its debugging mechanism. The API key remains hidden-input
and memory-only.

### Structured-output contract

The OpenAI schema adds supported constraints that already exist in local
validation, including non-empty episode and evidence arrays. Episode-ID string
fields are restricted to the IDs supplied in that individual request wherever
the schema remains within provider limits.

Cross-field invariants remain local because JSON Schema cannot conveniently
express them:

- each episode is allocated exactly once across workstreams and `unassigned`;
- topic and outcome evidence belongs to that workstream;
- merge output allocates each provisional workstream exactly once;
- merge output cannot strengthen an outcome.

The local validator remains authoritative. It exposes a stable, content-free
error code and field path, never the invalid value. Examples include
`empty_episode_ids`, `duplicate_episode_id`, `unknown_evidence_id`,
`cross_workstream_evidence`, and `incomplete_episode_allocation`.

### Diagnostics and support artifacts

Normal failure output includes:

- DayTrace version;
- provider and model;
- summary stage (`chunk` or `merge`);
- provider response ID and request ID when available;
- content-free local validation code and field path;
- request character count, episode count, and call index.

It excludes captured values and all request/response bodies.

An explicit debug-output option writes a versioned local JSON support artifact
containing the same metadata plus:

- supplied episode IDs;
- response allocation shape expressed only as IDs and collection sizes;
- placeholders and collection sizes for generated prose, not the prose itself;
- sanitization and validation counters.

The artifact is atomically written, visibly disclosed as potentially sensitive,
and never includes the API key, authorization headers, raw events, window titles,
URLs, paths, or model-generated prose. Diagnostic creation is opt-in; ordinary
runs retain no new local data.

### Failure and retry behavior

Release 0.3.2 does not automatically resend captured activity after a semantic
validation failure. It writes the deterministic fallback, emits the safe
diagnostic, and exits with status 2. Retry behavior belongs with the 0.4.0 input
and allocation redesign, where its safety and usefulness can be tested.

## Sanitized Recapture

After 0.3.2 is published, the user produces a session-level local artifact with
`--raw --format json`. The artifact is previewed before sharing and is processed
locally. It becomes an ephemeral acceptance input, not a repository fixture.

The recapture must demonstrate that no query, fragment, credential assignment,
email address, or raw filesystem path survived. If this check fails, compaction
work stops and the privacy boundary is fixed first.

## Release 0.4.0: Conservative Compaction and AI Reliability

### Anchor strength

Anchors have explicit strength rather than being treated as interchangeable:

- durable: repository, editor project, and safe document/file identity;
- contextual: specific conversation or task title;
- weak: generic application title, broad domain, search, inbox, new tab,
  assistant home, terminal, and operating-system surface.

Weak anchors never merge two strong sessions. They can join one neighboring
episode only under the existing short-gap rule and when there is no competing
durable anchor.

### Preventing transitive anchor chaining

An episode keeps a canonical durable-anchor set. A new strong session can join
only when it shares a compatible durable anchor with that canonical set; sharing
an incidental anchor with only the immediately preceding session is
insufficient. The canonical intersection cannot drift from repository A through
a mixed bridge session into repository B.

A session that simultaneously contains incompatible durable anchors is an
explicit ambiguity boundary. It remains a smaller mixed episode for the model
rather than causing neighboring episodes to merge through it.

Non-contiguous episodes may still be grouped into the same inferred workstream
by the model. Deterministic compaction only determines evidence units; it does
not define projects.

### Bounded evidence selection

Provider payloads preserve all durable anchors and outcome signals within small
hard limits. Contextual titles, domains, application counts, and activity labels
are ranked deterministically by recurrence, focused duration, specificity, and
first occurrence, then capped per episode. Generic and duplicate titles are
omitted.

If an episode exceeds the per-episode evidence budget after safe ranking,
DayTrace splits the evidence unit at a session boundary. It never truncates the
serialized request in the middle of a field.

The consent preview reports both the complete local episode count and the
provider-facing evidence counts so compression is observable.

### Allocation-oriented response design

The provider response separates classification from synthesis:

1. Each supplied episode receives exactly one provisional workstream key or the
   explicit unassigned value.
2. Topics and outcomes are synthesized for the resulting groups and cite only
   episode IDs assigned to that group.

The first pass uses a response shape whose required properties correspond to
the supplied episode IDs, preventing omissions where supported. The local
validator still checks duplicates, unknown IDs, and cross-group evidence.

When the provider returns a syntactically valid but semantically invalid
allocation, DayTrace may perform one repair call. The repair request contains
only IDs, group labels, validation codes, and allocation shape; it does not
resend episode titles or other captured content. There is never an unbounded
retry loop.

## Data Flow

```text
ActivityWatch
  -> normalize
  -> structural URL/text sanitization
  -> secret scan
  -> fuse observations
  -> sessionize
  -> conservative episode boundaries
  -> rank and bound provider evidence
  -> pre-egress privacy assertion
  -> OpenAI Responses API (store=false)
  -> strict JSON Schema validation
  -> DayTrace semantic validation
  -> optional allocation-only repair
  -> generated-text secret scan
  -> Markdown/JSON digest
  -> later Obsidian project mapping
```

## Compatibility

Release 0.3.2 is a patch release because it strengthens sanitization and
diagnostics without intentionally changing public report schemas. It may redact
more local title text, which is an intentional security correction.

Release 0.4.0 changes episode membership, provider schemas, and diagnostic JSON.
It therefore receives new versioned schema identifiers. Existing CLI option
names remain valid.

## Testing

### 0.3.2 acceptance

- Synthetic DNS, IPv4, IPv6, and localhost URLs lose query, fragment, userinfo,
  and credential values in local Markdown, local JSON, and provider payloads.
- A recording OpenAI client proves `store=False` on summary and merge calls.
- Provider schemas reject empty evidence and unknown IDs when expressible.
- Synthetic responses that pass provider schema but violate cross-field rules
  produce stable content-free validation codes.
- Failure support artifacts contain no captured text or generated prose.
- Existing deterministic fallback and atomic-write behavior remain unchanged.
- The complete test suite passes on every supported Python version.

### 0.4.0 acceptance

- The sanitized recapture conserves every session and exact active duration.
- No episode crosses between incompatible repositories through a mixed bridge
  session.
- Ambiguous sessions do not cause neighboring durable anchors to merge.
- Provider-facing title evidence is bounded per episode and the complete request
  is materially smaller than the 0.3.1 baseline.
- The representative day no longer contains a long episode dominated by
  unrelated anchors.
- Every final episode is assigned exactly once; every visible topic and outcome
  cites an episode in its workstream.
- A repair call, when needed, receives no captured title, domain, path, or
  application text and occurs at most once.

## Release Process

For each release:

1. add failing tests before implementation;
2. run the full suite and build wheel and source distributions;
3. inspect package contents and metadata;
4. commit directly to `main` as requested;
5. push `main`;
6. publish the package to PyPI;
7. create and push the matching version tag;
8. verify a clean public `uvx daytrace@<version>` installation.

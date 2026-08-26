# Data model, indexing, retention, and sync

## Storage principles

- SQLite is authoritative. Exports are reproducible projections.
- Persist extracted text and structured metadata only. “Text only” describes
  captured user content; the SQLite file and indexes are naturally binary.
- Store UTC instants plus the local calendar facts at capture time. Time-zone
  changes and daylight-saving transitions must not rewrite history.
- Entries are immutable except for user edits, redaction, duration extension,
  and tombstoning. Summaries retain evidence IDs.
- IDs are sortable UUIDv7/ULID-style values namespaced by device. Sync never
  depends on SQLite row IDs.

## Core schema sketch

```sql
CREATE TABLE observations (
  row_id             INTEGER PRIMARY KEY,
  id                 TEXT NOT NULL UNIQUE,
  device_id          TEXT NOT NULL,
  started_at_utc_ms  INTEGER NOT NULL,
  ended_at_utc_ms    INTEGER NOT NULL,
  local_date         TEXT NOT NULL,       -- YYYY-MM-DD at capture
  local_year         INTEGER NOT NULL,
  iso_week_year      INTEGER NOT NULL,
  iso_week           INTEGER NOT NULL,
  local_hour         INTEGER NOT NULL,
  day_part           TEXT NOT NULL,       -- morning/afternoon/evening/night
  utc_offset_minutes INTEGER NOT NULL,
  timezone_name      TEXT,
  source             TEXT NOT NULL,       -- screen/a11y/audio/window/input/browser
  app_id             TEXT,
  app_name           TEXT,
  window_title       TEXT,
  url_origin         TEXT,
  text               TEXT NOT NULL,
  language           TEXT,
  confidence         REAL,
  redaction_state    TEXT NOT NULL,
  policy_revision    INTEGER NOT NULL,
  content_hash       TEXT NOT NULL,
  metadata_json      TEXT NOT NULL DEFAULT '{}',
  created_at_utc_ms  INTEGER NOT NULL,
  CHECK (ended_at_utc_ms >= started_at_utc_ms)
);

CREATE INDEX observations_calendar
  ON observations(local_year, iso_week_year, iso_week, local_date,
                  day_part, started_at_utc_ms);
CREATE INDEX observations_time ON observations(started_at_utc_ms);
CREATE INDEX observations_app_time ON observations(app_id, started_at_utc_ms);
CREATE INDEX observations_source_time ON observations(source, started_at_utc_ms);
CREATE INDEX observations_dedupe
  ON observations(device_id, source, app_id, content_hash, started_at_utc_ms);

CREATE VIRTUAL TABLE observation_fts USING fts5(
  text,
  app_name,
  window_title,
  content='observations',
  content_rowid='row_id',
  tokenize='unicode61 remove_diacritics 2',
  prefix='2 3'
);
```

Final migrations must add external-content FTS insert/update/delete triggers and
test FTS consistency after every mutation. FTS query syntax must be parsed and
escaped by Daytrace; never concatenate an untrusted query into SQL.

Additional tables:

- `activity_segments`: coherent start/end ranges, label, evidence IDs, user
  edits, and segmenter version.
- `summaries`: period, generated/edited body, provider/model/schema version,
  evidence IDs, usage, and generation status.
- `consents`: source, state, timestamp, disclosure version, OS permission state,
  and policy revision. This is an audit for the user, not remote telemetry.
- `source_health`: last success/error, capability, permission, dropped work,
  and diagnostic code without captured content.
- `sync_queue`: export object ID/hash, attempt state, remote ref, and next retry.
- `tombstones`: durable deletion IDs for multi-device/export reconciliation.
- `settings`: non-secret typed settings with schema version. Secret references
  point to the OS vault.

## Hierarchical browsing

The UI hierarchy is a query projection:

```text
2026
└── ISO week 35
    └── Wednesday, August 26
        ├── Morning
        │   ├── 09:00–09:42  Project planning
        │   └── 09:42–10:15  Design review
        └── Afternoon
            └── 13:10–14:05  Implementation
```

The indexed `local_year`, `iso_week_year`, `iso_week`, `local_date`, `day_part`,
and time columns make this efficient without duplicating text into folders. ISO
week year is stored separately because dates near New Year can belong to the
adjacent ISO week year. Use half-open UTC ranges (`start <= t < end`) internally
and render using the stored local calendar facts.

Day-part defaults are local and configurable:

- morning 05:00–12:00;
- afternoon 12:00–17:00;
- evening 17:00–22:00;
- night 22:00–05:00.

Changing these boundaries affects future classification and query projection;
it does not silently rewrite stored history unless the user requests a rebuild.

## Dedupe and segmentation

Normalize Unicode and whitespace, strip configured volatile title fragments,
then hash source + app + normalized text. If a matching observation remains
active, extend its end time and increment an occurrence count instead of
writing duplicate text. Keep a short rolling MinHash/SimHash-style comparison
only in memory if near-duplicate detection is needed; do not add embeddings in
v1.

The segmenter starts a new activity on a configurable idle gap, major app/context
change, meeting boundary, or large text difference. It can merge brief context
switches. Store the algorithm version so upgrades can rebuild segments from
observations without changing raw journal text.

## Retention and deletion

Retention is per source (forever, one year, 90 days, 30 days, seven days, or
custom). A daily maintenance transaction:

1. selects expired observations in bounded batches;
2. records tombstones if sync is enabled;
3. deletes/rebuilds affected segments and summaries or marks them stale;
4. updates FTS through triggers;
5. checkpoints WAL and schedules incremental vacuum when idle.

User deletion takes priority over provider/sync retries. It cancels queued model
requests and prevents deleted text from being exported. “Delete everything”
closes the database, removes the database/WAL/backups and OS-vault items through
an explicit enumerated path, then verifies absence. Never construct deletion
targets from an unresolved environment variable.

## Backup and GitHub export

Do not sync `daytrace.sqlite`: Git performs poorly with a frequently changing
binary database, history retains deletions, and conflicts are not mergeable.

Generate deterministic paths instead:

```text
daytrace/
  README.md
  devices/<device-id>/2026/2026-W35/2026-08-26.jsonl
  summaries/2026/2026-W35/2026-08-26.md
  tombstones/<device-id>.jsonl
  manifest.json
```

- JSONL records use stable key ordering, UTC timestamps, schema version, text,
  metadata, and content hash. One device owns its daily shard.
- Markdown contains user-approved summaries by default, not every observation.
- Append or replace only the current device/day shard; seal previous days after
  a grace period. A late edit creates a deterministic replacement commit.
- Pull with rebase before push. Since devices own disjoint paths, ordinary use
  is conflict-free. Surface conflicts; never force-push.
- Queue offline work with exponential backoff and idempotency by export hash.
- A repository must be private unless the user overrides a high-friction
  warning. Private is not equivalent to end-to-end encrypted.
- Optional detailed export is encrypted locally with a recovery key the user
  controls. Store only ciphertext and a versioned envelope in Git.
- GitHub authorization should use a GitHub App authorization-code flow with
  PKCE, limited to selected repositories and contents access. Store tokens in
  the OS vault and never pass them as command-line arguments.

Useful upstream guidance: [GitHub recommends minimum permissions and secure
credential storage](https://docs.github.com/en/rest/authentication/keeping-your-api-credentials-secure)
and notes that native clients should prefer authorization code with PKCE over
device flow when possible.

## Backup semantics

GitHub export is not a transparent database restore. Provide two explicit
operations:

- **Import journal export:** validate schemas/hashes, respect tombstones, and
  rebuild observations/FTS/segments in a new database.
- **Encrypted local backup:** use SQLite's online backup API into an encrypted
  archive while writes continue, with a restore dry run and integrity check.

Never claim backup success until the remote object is verified or a local
restore test has passed.

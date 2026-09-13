# DayTrace

DayTrace turns ActivityWatch history into a compact, privacy-aware account of
what a day appears to contain: coherent activity episodes, inferred
projects/workstreams, broad topics, and evidence-backed achievements.

It is available in two forms from the same repository:

| Package | Install | Best for |
| --- | --- | --- |
| Python `daytrace` | `uv tool install daytrace@latest` | A ready-to-run ActivityWatch CLI |
| npm `@jmoraispk/daytrace` | `npm install @jmoraispk/daytrace` | Browser/Electron and Obsidian integrations |

Both implementations preserve the same versioned schemas and core semantics.
Python remains the reference implementation; synthetic parity fixtures keep the
TypeScript port aligned.

## From raw activity to a useful journal

DayTrace does not need project definitions to sanitize, fuse, sessionize, and
compact a day. Its deterministic stages first turn overlapping ActivityWatch
watchers into project-neutral episodes:

```text
ActivityWatch → normalize → remove AFK → sanitize → fuse overlaps
              → sessions → compact episodes → deterministic output
                                      ↘ optional AI workstream summary
```

In AI mode, the model groups those minimized episodes into inferred daily
workstreams and reports work/topics separately from apparent achievements. An
achievement is shown only when the trace contains evidence of a resulting
state—not merely because an application was open.

These workstreams are deliberately not canonical project definitions. An
Obsidian Second Brain plugin can map the validated daily digest onto the project
definitions stored in the vault. DayTrace therefore remains useful without
vault access, while Obsidian remains the source of truth for project identity.

## Privacy boundary

DayTrace processes locally unless AI mode is explicitly selected. Before a
cloud request it:

- removes AFK time and overlapping-duration inflation;
- normalizes and sanitizes titles, URLs, paths, email addresses, and secrets;
- sends compact episodes rather than raw ActivityWatch events;
- discloses the planned calls, input size, data categories, and estimated cost;
- asks for confirmation (`Continue? [Y/n]`);
- validates response structure, evidence, and complete episode allocation;
- secret-scans generated text before returning it.

The durable output contains text and structured metadata only. DayTrace does
not retain screenshots, audio, video, query strings, raw browser URLs, source
bucket IDs, source event IDs, or a duplicate ActivityWatch database.

## Python CLI

Install [uv](https://docs.astral.sh/uv/) and make sure ActivityWatch is running.
On Windows:

```powershell
winget install --id=astral-sh.uv -e
uv tool install daytrace@latest
uv tool update-shell
```

Open a new PowerShell window, then create a fully local report:

```powershell
daytrace activitywatch --date 2026-09-10 --output daytrace.md
```

For an AI-assisted workstream digest:

```powershell
daytrace activitywatch `
  --date 2026-09-10 `
  --summary ai `
  --provider openai `
  --model gpt-5.6-terra `
  --debug-output daytrace-ai-failure.json `
  --output daytrace.md
```

The CLI asks for the OpenAI API key in a hidden prompt after you approve the
disclosed request. The key is held in memory only. Do not put it in command-line
arguments or paste it into logs. OpenAI requests use `store=False`.

For a one-off run without persistent installation:

```powershell
uvx --refresh --link-mode=copy daytrace@latest activitywatch `
  --date 2026-09-10 --output daytrace.md
```

To install into a specific directory instead:

```powershell
mkdir C:\Tools\daytrace
cd C:\Tools\daytrace
uv venv
uv pip install daytrace
.\.venv\Scripts\daytrace.exe activitywatch --date 2026-09-10 --output daytrace.md
```

Useful CLI options:

- `--format json` writes a versioned structured handoff.
- `--details` adds sanitized episode allocation and evidence IDs.
- `--raw` adds the fine-grained sanitized audit trail; review it before sharing.
- `--diagnostics` emits aggregate, content-free coverage counts only.
- `--yes` confirms the disclosed cloud send for non-interactive workflows; key
  collection remains separate.
- `--timezone America/Los_Angeles` selects an explicit IANA timezone.
- `--server http://127.0.0.1:5600` overrides the default ActivityWatch server.

Interactive AI calls print content-free progress and an elapsed-seconds timer.
DayTrace allows one disclosed allocation-repair retry, then uses deterministic
fallback on failure. With `--debug-output`, the support artifact contains only
allow-listed structure and opaque identifiers—never prompt/response prose or
the API key. A successful output write ends with `Done!`.

The cost estimate uses the small, dated pricing table in the Python package.
Unknown models are reported as unavailable rather than guessed.

Python callers can use the same project-neutral core directly:

```python
from datetime import date

from daytrace.activitywatch import collect_day
from daytrace.markdown import render_episode_markdown

bundle = collect_day(date(2026, 9, 10), timezone_name="Europe/Lisbon")
markdown = render_episode_markdown(bundle)
```

## TypeScript core

Install the browser-compatible ESM package:

```bash
npm install @jmoraispk/daytrace
```

The package has zero runtime dependencies and no Node built-in imports. It is
designed for browser and Electron renderer environments, including an Obsidian
plugin. HTTP, credentials, persistence, UI, and scheduling remain host-owned.

```ts
import {
  collectDay,
  renderDigestMarkdown,
  renderEpisodeMarkdown,
  summarizeBundleOrFallback,
  type ActivityWatchTransport,
  type SummaryProvider,
} from "@jmoraispk/daytrace";

const activityWatchTransport: ActivityWatchTransport = {
  async request({ server, path, query, signal }) {
    const url = new URL(path, `${server}/`);
    for (const [key, value] of Object.entries(query ?? {})) {
      url.searchParams.set(key, value);
    }
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error("ActivityWatch request failed");
    return response.json();
  },
};

// The host adapter can reuse the API key already managed by your plugin.
declare const aiProvider: SummaryProvider;
declare const controller: AbortController;
declare function updateStatus(stage: string, elapsedSeconds: number): void;

const bundle = await collectDay({
  day: "2026-09-10",
  timezoneName: "Europe/Lisbon",
  server: "http://127.0.0.1:5600",
  transport: activityWatchTransport,
  signal: controller.signal,
  onProgress: ({ stage, elapsedSeconds }) => updateStatus(stage, elapsedSeconds),
});

const result = await summarizeBundleOrFallback(bundle, aiProvider, undefined, {
  signal: controller.signal,
  onProgress: ({ stage, elapsedSeconds }) => updateStatus(stage, elapsedSeconds),
});

const markdown = result.kind === "ai"
  ? renderDigestMarkdown(bundle, result.digest, result.provenance)
  : renderEpisodeMarkdown(result.bundle);
```

If the consuming plugin should keep the shorter `"daytrace"` import specifier,
install the scoped package under an npm alias:

```bash
npm install daytrace@npm:@jmoraispk/daytrace@^0.4.0
```

The plugin can then import the same API from `"daytrace"`.

The two injected boundaries are intentionally small:

```ts
interface ActivityWatchTransport {
  request(input: {
    server: string;
    path: string;
    query?: Readonly<Record<string, string>>;
    signal?: AbortSignal;
  }): Promise<unknown>;
}

interface SummaryProvider {
  complete(
    request: {
      passKind: "chunk" | "merge";
      payload: Readonly<Record<string, unknown>>;
      instructions: string;
      responseFormat: Readonly<Record<string, unknown>>;
    },
    options?: { signal?: AbortSignal },
  ): Promise<{
    payload: unknown;
    provider: string;
    model: string;
    inputTokens?: number;
    outputTokens?: number;
    responseId?: string;
    requestId?: string;
  }>;
}
```

Core public operations include:

| API | Purpose |
| --- | --- |
| `collectDay(options)` | Query through an injected transport and produce an episode bundle |
| `buildSummaryPlan(bundle)` | Inspect minimized requests before any AI call |
| `summarizeBundle(bundle, provider, plan?, options?)` | Return only a validated AI digest or throw a typed safe error |
| `summarizeBundleOrFallback(...)` | Return a discriminated AI/deterministic result |
| `renderEpisodeJson/Markdown(...)` | Render deterministic `episode-bundle.v1` output |
| `renderDigestJson/Markdown(...)` | Render AI-assisted `workstream-report.v2` output |
| `renderSummaryFailureJson(failure)` | Render a content-free `ai-failure.v1` artifact |
| `DAYTRACE_VERSION` | Package/core version |

The package also exports the reusable deterministic stages (`normalizeEvents`,
`removeAfk`, `sanitizeRecords`, `fuseObservations`, `sessionize`, and
`compactSessions`), strict validators, domain types, and the inspectable summary
prompts. See the [npm package guide](packages/daytrace-core/README.md) for the
complete integration contract.

## Schemas and fallback

The stable serialized contracts are:

- `daytrace.episode-bundle.v1`
- `daytrace.workstream-report.v2`
- `daytrace.summary-request.v2`
- `daytrace.workstream-digest.v2`
- `daytrace.workstream-merge-request.v1`
- `daytrace.workstream-merge.v1`
- `daytrace.ai-failure.v1`

Every AI topic and visible outcome cites supplied episode IDs. An episode can be
evidence for multiple narrative claims, but it has exactly one primary
allocation across workstreams or the unassigned list. Durations always come
from that deterministic primary allocation.

## Development

```bash
# Python
uv sync --all-groups
uv run pytest
uv build --no-sources

# TypeScript
npm --prefix packages/daytrace-core ci
npm --prefix packages/daytrace-core test
npm --prefix packages/daytrace-core run typecheck
npm --prefix packages/daytrace-core run build
npm --prefix packages/daytrace-core run smoke:browser
```

The parity adapter writes only invented fixture data under
`tests/fixtures/cross-language/`. Never commit personal ActivityWatch exports.

## Product and architecture notes

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model and search](docs/DATA_MODEL.md)
- [Privacy and security](docs/PRIVACY_SECURITY.md)
- [Product and UX specification](docs/PRODUCT_UX.md)
- [Screenpipe reuse audit](docs/SCREENPIPE_REUSE.md)
- [ActivityWatch integration research](docs/ACTIVITYWATCH_INTEGRATION_RESEARCH.md)
- [TypeScript core design](docs/superpowers/specs/2026-09-13-typescript-core-design.md)

## License

MIT

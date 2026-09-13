# daytrace

Browser-compatible DayTrace core for turning ActivityWatch events into compact,
privacy-aware daily activity episodes and validated AI workstream summaries.

```bash
npm install @jmoraispk/daytrace
```

`@jmoraispk/daytrace` is ESM-only, ships TypeScript declarations, has zero runtime
dependencies, and bundles for browser/Electron environments without Node
polyfills. It is the reusable core intended for integrations such as an Obsidian
Second Brain plugin.

## What it does

The deterministic pipeline normalizes ActivityWatch events, removes AFK time,
redacts sensitive text, fuses overlapping watcher sources, builds sessions, and
compacts them into project-neutral episodes. This part needs neither project
definitions nor an AI provider.

An optional second stage sends only minimized episode evidence through an
injected provider. DayTrace plans bounded chunks, validates the structured
response and every evidence reference, allows one allocation-repair attempt,
merges cross-chunk workstreams, performs a final privacy check, and returns only
validated summaries. `summarizeBundleOrFallback` returns the deterministic
episode bundle when that process fails.

The library contains no API-key handling, OpenAI SDK, ActivityWatch client, UI,
vault access, filesystem access, scheduling, subprocesses, or Node runtime
access. Those concerns belong to the host.

## Quick start

```ts
import {
  collectDay,
  renderDigestMarkdown,
  renderEpisodeMarkdown,
  summarizeBundleOrFallback,
  type ActivityWatchTransport,
  type SummaryProvider,
} from "@jmoraispk/daytrace";

const transport: ActivityWatchTransport = {
  async request({ server, path, query, signal }) {
    const url = new URL(path, `${server}/`);
    Object.entries(query ?? {}).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error("ActivityWatch request failed");
    return response.json();
  },
};

declare const provider: SummaryProvider; // Implemented by your host/plugin.
declare const controller: AbortController;

const bundle = await collectDay({
  day: "2026-09-10",
  timezoneName: "Europe/Lisbon",
  server: "http://127.0.0.1:5600",
  transport,
  signal: controller.signal,
  onProgress: ({ stage, elapsedSeconds }) => {
    console.log(stage, elapsedSeconds);
  },
});

const result = await summarizeBundleOrFallback(bundle, provider, undefined, {
  signal: controller.signal,
});

const markdown = result.kind === "ai"
  ? renderDigestMarkdown(bundle, result.digest, result.provenance)
  : renderEpisodeMarkdown(result.bundle);
```

To retain a shorter `"daytrace"` import in an existing consumer, install it as
an npm alias:

```bash
npm install daytrace@npm:@jmoraispk/daytrace@^0.4.0
```

An Obsidian plugin can implement `SummaryProvider.complete` with the key and
network layer it already owns. DayTrace supplies the minimized payload, exact
instructions, strict response format, pass kind, and optional abort signal.

## Injected interfaces

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

Provider errors must not include secrets in returned metadata. DayTrace drops
arbitrary thrown messages and keeps only typed, allow-listed failure fields.

## Public API

Primary orchestration and rendering:

- `collectDay(options)`
- `buildSummaryPlan(bundle, options?)`
- `buildSummaryRequest(bundle)`
- `buildMergeRequest(digests, options?)`
- `summarizeBundle(bundle, provider, plan?, options?)`
- `summarizeBundleOrFallback(bundle, provider, plan?, options?)`
- `renderEpisodeJson(bundle, options?)`
- `renderEpisodeMarkdown(bundle, options?)`
- `renderSessionJson(bundle, options?)`
- `renderSessionMarkdown(bundle, options?)`
- `renderDigestJson(bundle, digest, provenance, options?)`
- `renderDigestMarkdown(bundle, digest, provenance, options?)`
- `renderSummaryFailureJson(failure)`
- `DAYTRACE_VERSION`

Reusable deterministic stages:

- `normalizeEvents`
- `removeAfk`
- `sanitizeRecords`
- `fuseObservations`
- `sessionize`
- `compactSessions`
- `buildReport`

Validation and privacy:

- `assertCloudSafePayload`
- `validateDigest`
- `validateMerge`
- `validateFinalAllocation`
- `safeResponseShape`
- `SYSTEM_PROMPT` and `MERGE_SYSTEM_PROMPT`

All corresponding domain types and content-free error classes are exported.

## Cancellation and progress

Pass an `AbortSignal` to collection or summarization. Cancellation is checked
before and after injected calls and between stages; an abort is rethrown and is
never converted into deterministic fallback.

Progress callbacks contain only fixed stage names, counts, and integer elapsed
seconds. They never contain bucket/event IDs, titles, URLs, paths, prompts,
responses, or credentials.

## Schemas

The package preserves the Python contracts:

- `daytrace.episode-bundle.v1`
- `daytrace.workstream-report.v2`
- `daytrace.summary-request.v2`
- `daytrace.workstream-digest.v2`
- `daytrace.workstream-merge-request.v1`
- `daytrace.workstream-merge.v1`
- `daytrace.ai-failure.v1`

Python is the reference implementation. Committed synthetic fixtures verify
cross-language durations, sessions, episodes, diagnostics, privacy redaction,
DST boundaries, schemas, summary planning, and rendered Markdown/JSON.

## Development

From the repository root:

```bash
npm --prefix packages/daytrace-core ci
npm --prefix packages/daytrace-core test
npm --prefix packages/daytrace-core run typecheck
npm --prefix packages/daytrace-core run build
npm --prefix packages/daytrace-core run pack:check
npm --prefix packages/daytrace-core run smoke:browser
```

The browser smoke test packs the package, installs it in a temporary consumer,
imports the built ESM, and bundles it with esbuild for `platform: "browser"`
without polyfills.

## License

MIT

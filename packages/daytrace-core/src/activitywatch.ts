import { DiagnosticCollector } from "./diagnostics.js";
import { compactSessions } from "./episode.js";
import { fuseObservations } from "./fusion.js";
import type {
  ActivityRecord,
  ActivityWatchTransport,
  EpisodeBundle,
  IsoDate,
  ProgressCallback,
  ProgressStage,
} from "./models.js";
import { SUPPORTED_BUCKET_TYPES, normalizeEvents } from "./normalize.js";
import { sanitizeRecords } from "./sanitize.js";
import { sessionize } from "./sessionize.js";
import { ActivityWatchSource } from "./source.js";
import { resolveDay } from "./time.js";
import { removeAfk } from "./transform.js";

export const DEFAULT_SERVER = "http://127.0.0.1:5600";

export interface CollectDayOptions {
  readonly day: IsoDate;
  readonly transport: ActivityWatchTransport;
  readonly server?: string;
  readonly timezoneName?: string;
  readonly signal?: AbortSignal;
  readonly onProgress?: ProgressCallback;
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  signal?.throwIfAborted();
}

export async function collectDay(options: CollectDayOptions): Promise<EpisodeBundle> {
  const startedAt = performance.now();
  const emit = (stage: ProgressStage, current?: number, total?: number): void => {
    options.onProgress?.({
      stage,
      elapsedSeconds: Math.max(0, Math.floor((performance.now() - startedAt) / 1000)),
      ...(current === undefined ? {} : { current }),
      ...(total === undefined ? {} : { total }),
    });
  };
  const timezoneName = options.timezoneName
    ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const window = resolveDay(options.day, timezoneName);
  const source = new ActivityWatchSource(options.server ?? DEFAULT_SERVER, options.transport);
  const diagnostics = new DiagnosticCollector();

  throwIfAborted(options.signal);
  await source.getInfo(options.signal);
  throwIfAborted(options.signal);
  emit("activitywatch:info");

  const buckets = await source.listBuckets(options.signal);
  throwIfAborted(options.signal);
  emit("activitywatch:buckets", buckets.length, buckets.length);
  const supported = buckets.filter((bucket) => bucket.type in SUPPORTED_BUCKET_TYPES);
  const unknownCount = buckets.length - supported.length;
  if (unknownCount > 0) diagnostics.add("unsupported-bucket", unknownCount);

  const records: ActivityRecord[] = [];
  for (const bucket of supported) {
    throwIfAborted(options.signal);
    const events = await source.getEvents(bucket.id, window.start, window.end, options.signal);
    throwIfAborted(options.signal);
    records.push(...normalizeEvents(bucket, events, window, (code) => diagnostics.add(code)));
  }
  emit("activitywatch:events", supported.length, supported.length);
  throwIfAborted(options.signal);
  emit("pipeline:normalize", records.length, records.length);

  const active = removeAfk(records);
  throwIfAborted(options.signal);
  const sanitized = sanitizeRecords(active, (code) => diagnostics.add(code));
  emit("pipeline:sanitize", sanitized.length, sanitized.length);

  throwIfAborted(options.signal);
  const slices = fuseObservations(sanitized, (code) => diagnostics.add(code));
  emit("pipeline:fuse", slices.length, slices.length);

  throwIfAborted(options.signal);
  const sessions = sessionize(options.day, window, slices, diagnostics.snapshot());
  emit("pipeline:sessions", sessions.sessions.length, sessions.sessions.length);

  throwIfAborted(options.signal);
  const episodes = compactSessions(sessions);
  emit("pipeline:episodes", episodes.episodes.length, episodes.episodes.length);
  throwIfAborted(options.signal);
  emit("complete");
  return episodes;
}

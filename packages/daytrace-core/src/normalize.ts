import { DaytraceInputError } from "./models.js";
import type {
  ActivityRecord,
  DayWindow,
  DiagnosticCode,
  RawBucket,
  RawEvent,
  SourceKind,
} from "./models.js";
import { timestampMs } from "./time.js";

export const SUPPORTED_BUCKET_TYPES: Readonly<Record<string, SourceKind>> = {
  currentwindow: "current-window",
  afkstatus: "afk",
  "app.editor.activity": "editor",
  "web.tab.current": "browser",
};

const ZONED_TIMESTAMP = /(?:Z|[+-]\d{2}:?\d{2})$/i;

function text(data: Readonly<Record<string, unknown>>, key: string): string | undefined {
  const value = data[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function urlParts(data: Readonly<Record<string, unknown>>): {
  readonly urlHost?: string;
  readonly urlPath?: string;
} {
  const value = text(data, "url");
  if (value === undefined) return {};
  try {
    const parsed = new URL(value);
    return {
      ...(parsed.hostname.length === 0 ? {} : { urlHost: parsed.hostname.toLocaleLowerCase() }),
      ...(parsed.pathname.length === 0 ? {} : { urlPath: parsed.pathname }),
    };
  } catch {
    return {};
  }
}

function compareRecords(left: ActivityRecord, right: ActivityRecord): number {
  return timestampMs(left.start) - timestampMs(right.start)
    || left.bucketId.localeCompare(right.bucketId)
    || left.eventId.localeCompare(right.eventId);
}

export function normalizeEvents(
  bucket: RawBucket,
  events: readonly RawEvent[],
  window: DayWindow,
  warn: (code: DiagnosticCode) => void,
): readonly ActivityRecord[] {
  const kind = SUPPORTED_BUCKET_TYPES[bucket.type];
  if (kind === undefined) {
    throw new DaytraceInputError("unsupported-bucket", "unsupported ActivityWatch bucket");
  }
  const windowStart = timestampMs(window.start);
  const windowEnd = timestampMs(window.end);
  const normalized: ActivityRecord[] = [];
  for (const event of events) {
    if (!ZONED_TIMESTAMP.test(event.timestamp)) {
      warn("naive-timestamp");
      continue;
    }
    let rawStart: number;
    try {
      rawStart = timestampMs(event.timestamp);
    } catch {
      warn("naive-timestamp");
      continue;
    }
    const start = Math.max(rawStart, windowStart);
    const end = Math.min(rawStart + event.durationSeconds * 1000, windowEnd);
    if (end <= start) {
      warn("non-positive-event");
      continue;
    }
    const parts = urlParts(event.data);
    const app = text(event.data, "app");
    const title = text(event.data, "title");
    const project = text(event.data, "project");
    const file = text(event.data, "file");
    const language = text(event.data, "language");
    const status = text(event.data, "status");
    normalized.push({
      eventId: event.id,
      bucketId: bucket.id,
      kind,
      start: new Date(start).toISOString(),
      end: new Date(end).toISOString(),
      ...(app === undefined ? {} : { app }),
      ...(title === undefined ? {} : { title }),
      ...(project === undefined ? {} : { project }),
      ...(file === undefined ? {} : { file }),
      ...parts,
      ...(language === undefined ? {} : { language }),
      ...(status === undefined ? {} : { status }),
    });
  }
  return normalized.sort(compareRecords);
}

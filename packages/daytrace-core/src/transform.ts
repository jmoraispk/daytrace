import type { ActivityRecord } from "./models.js";
import { timestampMs } from "./time.js";

type Interval = readonly [number, number];

function compareRecords(left: ActivityRecord, right: ActivityRecord): number {
  return timestampMs(left.start) - timestampMs(right.start)
    || left.bucketId.localeCompare(right.bucketId)
    || left.eventId.localeCompare(right.eventId);
}

function sorted(records: readonly ActivityRecord[]): ActivityRecord[] {
  return [...records].sort(compareRecords);
}

function union(intervals: readonly Interval[]): Interval[] {
  const merged: Interval[] = [];
  for (const [start, end] of [...intervals].sort((left, right) => left[0] - right[0] || left[1] - right[1])) {
    const previous = merged.at(-1);
    if (previous === undefined || start > previous[1]) {
      merged.push([start, end]);
    } else {
      merged[merged.length - 1] = [previous[0], Math.max(previous[1], end)];
    }
  }
  return merged;
}

function subtractInterval(fragments: readonly Interval[], awayStart: number, awayEnd: number): Interval[] {
  const output: Interval[] = [];
  for (const [start, end] of fragments) {
    if (awayEnd <= start || awayStart >= end) {
      output.push([start, end]);
      continue;
    }
    if (start < awayStart) output.push([start, awayStart]);
    if (awayEnd < end) output.push([awayEnd, end]);
  }
  return output;
}

export function removeAfk(records: readonly ActivityRecord[]): readonly ActivityRecord[] {
  const away = union(records
    .filter((item) => item.kind === "afk" && (item.status ?? "").toLocaleLowerCase() === "afk")
    .map((item) => [timestampMs(item.start), timestampMs(item.end)] as const));
  const output: ActivityRecord[] = [];
  for (const item of records) {
    if (item.kind === "afk") continue;
    let fragments: Interval[] = [[timestampMs(item.start), timestampMs(item.end)]];
    for (const [awayStart, awayEnd] of away) {
      fragments = subtractInterval(fragments, awayStart, awayEnd);
    }
    for (const [start, end] of fragments) {
      output.push({ ...item, start: new Date(start).toISOString(), end: new Date(end).toISOString() });
    }
  }
  return output.sort(compareRecords);
}

export function filterProject(records: readonly ActivityRecord[], project?: string): readonly ActivityRecord[] {
  if (project === undefined) return sorted(records);
  const needle = project.toLocaleLowerCase();
  return sorted(records.filter((item) => [
    item.project,
    item.app,
    item.title,
    item.file,
    item.urlHost,
    item.bucketId,
  ].some((value) => value?.toLocaleLowerCase().includes(needle) === true)));
}

function contentKey(item: ActivityRecord): string {
  return JSON.stringify([
    item.bucketId,
    item.kind,
    item.app ?? null,
    item.title ?? null,
    item.project ?? null,
    item.file ?? null,
    item.urlHost ?? null,
    item.urlPath ?? null,
    item.language ?? null,
    item.status ?? null,
  ]);
}

export function mergeAdjacent(
  records: readonly ActivityRecord[],
  maximumGapSeconds = 60,
): readonly ActivityRecord[] {
  const byBucket = new Map<string, ActivityRecord[]>();
  for (const item of sorted(records)) {
    const bucket = byBucket.get(item.bucketId) ?? [];
    const previous = bucket.at(-1);
    if (
      previous !== undefined
      && contentKey(previous) === contentKey(item)
      && timestampMs(item.start) - timestampMs(previous.end) <= maximumGapSeconds * 1000
    ) {
      bucket[bucket.length - 1] = {
        ...previous,
        end: timestampMs(previous.end) >= timestampMs(item.end) ? previous.end : item.end,
      };
    } else {
      bucket.push(item);
    }
    byBucket.set(item.bucketId, bucket);
  }
  return [...byBucket.values()].flat().sort(compareRecords);
}

export interface WindowAllocation {
  readonly record: ActivityRecord;
  readonly seconds: number;
}

export function partitionWindowSeconds(records: readonly ActivityRecord[]): readonly WindowAllocation[] {
  const windows = records.filter((item) => item.kind === "current-window");
  const boundaries = [...new Set(windows.flatMap((item) => [timestampMs(item.start), timestampMs(item.end)]))]
    .sort((left, right) => left - right);
  const totals = new Map<ActivityRecord, number>();
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index];
    const end = boundaries[index + 1];
    if (start === undefined || end === undefined) continue;
    const candidates = windows.filter((item) => timestampMs(item.start) < end && timestampMs(item.end) > start)
      .sort((left, right) => left.bucketId.localeCompare(right.bucketId) || left.eventId.localeCompare(right.eventId));
    const winner = candidates[0];
    if (winner !== undefined) totals.set(winner, (totals.get(winner) ?? 0) + (end - start) / 1000);
  }
  return [...totals.entries()]
    .sort(([left], [right]) => left.bucketId.localeCompare(right.bucketId) || left.eventId.localeCompare(right.eventId))
    .map(([record, seconds]) => ({ record, seconds }));
}

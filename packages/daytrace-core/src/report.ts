import type {
  ActivityRecord,
  ActivityReport,
  ApplicationTotal,
  DayWindow,
  IsoDate,
  SourceKind,
} from "./models.js";
import { timestampMs } from "./time.js";
import { partitionWindowSeconds } from "./transform.js";

const SOURCE_ORDER: Readonly<Record<SourceKind, number>> = {
  "current-window": 0,
  editor: 1,
  browser: 2,
  afk: 3,
};

export function buildReport(
  day: IsoDate,
  window: DayWindow,
  records: readonly ActivityRecord[],
  project?: string,
): ActivityReport {
  const timeline = [...records].sort(
    (left, right) => timestampMs(left.start) - timestampMs(right.start)
      || left.bucketId.localeCompare(right.bucketId)
      || left.eventId.localeCompare(right.eventId),
  );
  const allocation = partitionWindowSeconds(timeline);
  const appSeconds = new Map<string, number>();
  for (const { record, seconds } of allocation) {
    const app = record.app ?? "Unknown application";
    appSeconds.set(app, (appSeconds.get(app) ?? 0) + seconds);
  }
  const applications: ApplicationTotal[] = [...appSeconds.entries()]
    .sort(([leftApp, leftSeconds], [rightApp, rightSeconds]) => rightSeconds - leftSeconds
      || leftApp.toLocaleLowerCase().localeCompare(rightApp.toLocaleLowerCase())
      || leftApp.localeCompare(rightApp))
    .map(([app, seconds]) => ({ app, seconds }));
  const sources = [...new Set(timeline.map((item) => item.kind))]
    .sort((left, right) => SOURCE_ORDER[left] - SOURCE_ORDER[right]);
  return {
    day,
    timezoneName: window.timezoneName,
    ...(project === undefined ? {} : { project }),
    ...(allocation.length === 0 ? {} : { activeSeconds: applications.reduce((total, item) => total + item.seconds, 0) }),
    sources,
    timeline,
    applications,
  };
}

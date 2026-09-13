import { describe, expect, it } from "vitest";

import { removeAfk } from "../src/transform.js";
import type { ActivityRecord } from "../src/models.js";

const windowRecord: ActivityRecord = {
  eventId: "window-1",
  bucketId: "window",
  kind: "current-window",
  start: "2026-09-10T09:00:00.000Z",
  end: "2026-09-10T09:30:00.000Z",
  app: "Code",
  title: "Demo",
};

describe("removeAfk", () => {
  it("splits active records around touching AFK intervals", () => {
    const records: ActivityRecord[] = [
      windowRecord,
      { eventId: "afk-1", bucketId: "afk", kind: "afk", start: "2026-09-10T09:05:00.000Z", end: "2026-09-10T09:10:00.000Z", status: "afk" },
      { eventId: "afk-2", bucketId: "afk", kind: "afk", start: "2026-09-10T09:10:00.000Z", end: "2026-09-10T09:15:00.000Z", status: "AFK" },
    ];

    expect(removeAfk(records).map(({ start, end }) => ({ start, end }))).toEqual([
      { start: "2026-09-10T09:00:00.000Z", end: "2026-09-10T09:05:00.000Z" },
      { start: "2026-09-10T09:15:00.000Z", end: "2026-09-10T09:30:00.000Z" },
    ]);
  });

  it("does not remove not-afk time", () => {
    const active: ActivityRecord = {
      eventId: "afk-active",
      bucketId: "afk",
      kind: "afk",
      start: windowRecord.start,
      end: windowRecord.end,
      status: "not-afk",
    };
    expect(removeAfk([windowRecord, active])).toEqual([windowRecord]);
  });
});

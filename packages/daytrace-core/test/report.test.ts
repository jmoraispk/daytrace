import { describe, expect, it } from "vitest";

import { buildReport } from "../src/report.js";
import type { ActivityRecord } from "../src/models.js";

describe("buildReport", () => {
  it("allocates overlapping foreground time only once", () => {
    const records: ActivityRecord[] = [
      { eventId: "z", bucketId: "z-window", kind: "current-window", start: "2026-09-10T09:00:00Z", end: "2026-09-10T09:20:00Z", app: "Firefox" },
      { eventId: "a", bucketId: "a-window", kind: "current-window", start: "2026-09-10T09:10:00Z", end: "2026-09-10T09:30:00Z", app: "Code" },
    ];
    const report = buildReport("2026-09-10", {
      timezoneName: "UTC",
      start: "2026-09-10T00:00:00Z",
      end: "2026-09-11T00:00:00Z",
    }, records);

    expect(report.activeSeconds).toBe(1800);
    expect(report.applications).toEqual([
      { app: "Code", seconds: 1200 },
      { app: "Firefox", seconds: 600 },
    ]);
  });
});

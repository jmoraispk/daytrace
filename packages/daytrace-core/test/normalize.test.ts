import { describe, expect, it } from "vitest";

import { normalizeEvents } from "../src/normalize.js";
import type { DiagnosticCode, RawBucket, RawEvent } from "../src/models.js";

const bucket: RawBucket = {
  id: "window",
  type: "currentwindow",
  client: "test",
  hostname: "test",
};
const window = {
  timezoneName: "UTC",
  start: "2026-09-10T00:00:00.000Z",
  end: "2026-09-11T00:00:00.000Z",
};

describe("normalizeEvents", () => {
  it("clips, sorts, and reports non-positive records", () => {
    const warnings: DiagnosticCode[] = [];
    const events: RawEvent[] = [
      { id: "later", timestamp: "2026-09-10T12:00:00Z", durationSeconds: 60, data: { app: "Code" } },
      { id: "cross", timestamp: "2026-09-09T23:59:00Z", durationSeconds: 120, data: { app: "Code" } },
      { id: "end", timestamp: "2026-09-11T00:00:00Z", durationSeconds: 0, data: { app: "Code" } },
    ];

    const result = normalizeEvents(bucket, events, window, (code) => warnings.push(code));

    expect(result.map(({ eventId, start, end }) => ({ eventId, start, end }))).toEqual([
      { eventId: "cross", start: "2026-09-10T00:00:00.000Z", end: "2026-09-10T00:01:00.000Z" },
      { eventId: "later", start: "2026-09-10T12:00:00.000Z", end: "2026-09-10T12:01:00.000Z" },
    ]);
    expect(warnings).toEqual(["non-positive-event"]);
  });

  it("retains browser host/path but never query or fragment", () => {
    const browser = { ...bucket, id: "web", type: "web.tab.current" };
    const [record] = normalizeEvents(browser, [{
      id: "web-1",
      timestamp: "2026-09-10T12:00:00Z",
      durationSeconds: 60,
      data: { url: "https://github.com/octo/demo/issues/1?code=secret#token", title: "repository" },
    }], window, () => undefined);

    expect(record?.urlHost).toBe("github.com");
    expect(record?.urlPath).toBe("/octo/demo/issues/1");
    expect(JSON.stringify(record)).not.toContain("secret");
  });
});

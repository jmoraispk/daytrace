import { describe, expect, it } from "vitest";

import { resolveDay } from "../src/time.js";

describe("resolveDay", () => {
  it("builds a half-open UTC window for an ordinary day", () => {
    expect(resolveDay("2026-09-10", "America/Los_Angeles")).toEqual({
      timezoneName: "America/Los_Angeles",
      start: "2026-09-10T07:00:00.000Z",
      end: "2026-09-11T07:00:00.000Z",
    });
  });

  it("preserves spring and autumn DST day lengths", () => {
    const spring = resolveDay("2026-03-08", "America/Los_Angeles");
    const autumn = resolveDay("2026-11-01", "America/Los_Angeles");

    expect(Date.parse(spring.end) - Date.parse(spring.start)).toBe(23 * 60 * 60 * 1000);
    expect(Date.parse(autumn.end) - Date.parse(autumn.start)).toBe(25 * 60 * 60 * 1000);
  });

  it("rejects invalid dates and time zones without echoing input", () => {
    expect(() => resolveDay("2026-02-30", "UTC")).toThrow("invalid day");
    expect(() => resolveDay("2026-09-10", "Private/Workspace"))
      .toThrow("invalid timezone");
  });
});

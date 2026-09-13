import { describe, expect, it } from "vitest";

import { sessionize } from "../src/sessionize.js";
import { iso, slice } from "./pipeline-factories.js";

const window = {
  timezoneName: "UTC",
  start: "2026-09-10T00:00:00.000Z",
  end: "2026-09-11T00:00:00.000Z",
};

describe("sessionize", () => {
  it("bridges a short generic interruption between matching anchors", () => {
    const result = sessionize("2026-09-10", window, [
      slice(0, 5, { title: "PerfLife", urlPath: "/octo/demo" }),
      slice(5, 10 / 60, { app: "Slack", title: "Slack" }),
      slice(5 + 10 / 60, 5, { title: "PerfLife", urlPath: "/octo/demo" }),
    ], []);

    expect(result.sessions).toHaveLength(1);
    expect(result.sessions[0]?.label).toBe("octo/demo");
    expect(result.sessions[0]?.activeSeconds).toBe(610);
  });

  it("splits after idle gaps and strong anchor changes", () => {
    const result = sessionize("2026-09-10", window, [
      slice(0, 5, { urlPath: "/octo/alpha" }),
      slice(11, 5, { urlPath: "/octo/alpha" }),
      slice(16, 5, { urlPath: "/octo/beta" }),
    ], []);

    expect(result.sessions.map((item) => item.label)).toEqual([
      "octo/alpha",
      "octo/alpha",
      "octo/beta",
    ]);
    expect(result.sessions.map((item) => item.sessionId)).toEqual([
      "session-001",
      "session-002",
      "session-003",
    ]);
  });

  it("detects bounded outcome signals", () => {
    const result = sessionize("2026-09-10", window, [
      slice(0, 1, { title: "New repository", urlHost: "github.com" }),
      slice(1, 2, { title: "octo/demo", urlPath: "/octo/demo" }),
      slice(3, 1, { title: "Success Page", urlHost: "lab.example" }),
      slice(4, 1, { app: "demo-installer.exe", title: "Installation Options" }),
    ], []);

    expect(new Set(result.sessions.flatMap((item) => item.outcomeSignals.map((signal) => signal.code))))
      .toEqual(new Set(["named-repository-appeared", "checkout-success", "installer-started"]));
    expect(result.sessions[0]?.start).toBe(iso(0));
  });
});

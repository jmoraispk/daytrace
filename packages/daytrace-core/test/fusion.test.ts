import { describe, expect, it } from "vitest";

import { fuseObservations } from "../src/fusion.js";
import { observation } from "./pipeline-factories.js";

describe("fuseObservations", () => {
  it("uses foreground time as authority and attaches matching browser context", () => {
    const window = observation(0, 10, { app: "msedge.exe", title: "PerfLife" });
    const browser = observation(2, 5, {
      evidenceId: "evidence-0002",
      kind: "browser",
      app: undefined,
      title: "octo/demo",
      urlHost: "github.com",
      urlPath: "/octo/demo",
    });

    const slices = fuseObservations([window, browser], () => undefined);

    expect(slices.map(({ start, end }) => [start, end])).toHaveLength(3);
    expect(slices[1]?.contexts[0]?.urlPath).toBe("/octo/demo");
    expect(slices.reduce((total, item) => total + (Date.parse(item.end) - Date.parse(item.start)) / 1000, 0)).toBe(600);
  });

  it("chooses a stable winner and emits a content-free conflict diagnostic", () => {
    const diagnostics: string[] = [];
    const slices = fuseObservations([
      observation(0, 5, { evidenceId: "evidence-0002", app: "Firefox" }),
      observation(0, 5, { evidenceId: "evidence-0001", app: "Code" }),
    ], (code) => diagnostics.push(code));

    expect(slices[0]?.app).toBe("Code");
    expect(diagnostics).toEqual(["window-conflict"]);
  });

  it("keeps browser-only activity as unfocused evidence", () => {
    const slices = fuseObservations([
      observation(0, 5, { kind: "browser", app: undefined, title: undefined, urlHost: "github.com", urlPath: "/octo/demo" }),
    ], () => undefined);

    expect(slices[0]?.focused).toBe(false);
    expect(slices[0]?.contexts[0]?.urlPath).toBe("/octo/demo");
  });
});

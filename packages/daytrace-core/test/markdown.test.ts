import { describe, expect, it } from "vitest";

import { compactSessions } from "../src/episode.js";
import { formatDuration, renderEpisodeMarkdown, renderMarkdown } from "../src/markdown.js";
import { buildReport } from "../src/report.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

describe("deterministic Markdown", () => {
  it.each([
    [1, "<1m"],
    [59.9, "<1m"],
    [60, "1m"],
    [89, "1m"],
    [90, "2m"],
    [3600, "1h"],
  ])("formats %s seconds as %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });

  it("renders compact episodes and escapes captured markup", () => {
    const bundle = compactSessions(sessionBundle([
      session("session-001", "<demo>", [slice(0, 10, { title: "<demo>", urlPath: "/octo/demo" })]),
    ]));
    const rendered = renderEpisodeMarkdown(bundle);

    expect(rendered).toContain("# DayTrace — 2026-09-10");
    expect(rendered).toContain("09:00–09:10");
    expect(rendered).toContain("Activity transitions: 1");
    expect(rendered).not.toContain("<demo>");
    expect(rendered).not.toContain("session-001");
    expect(rendered.endsWith("\n")).toBe(true);
  });

  it("renders a valid empty report", () => {
    const report = buildReport("2026-09-10", {
      timezoneName: "UTC",
      start: "2026-09-10T00:00:00Z",
      end: "2026-09-11T00:00:00Z",
    }, []);
    expect(renderMarkdown(report)).toMatch(/No matching activity\.\n$/);
  });
});

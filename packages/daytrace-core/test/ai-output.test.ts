import { describe, expect, it } from "vitest";

import { compactSessions } from "../src/episode.js";
import { renderDigestJson } from "../src/json-output.js";
import { renderDigestMarkdown } from "../src/markdown.js";
import type { SummaryProvenance, WorkstreamDigest } from "../src/models.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

const bundle = compactSessions(sessionBundle([
  session("session-001", "Demo", [slice(0, 10, { title: "Demo", project: "demo", file: "main.ts" })]),
]));
const digest: WorkstreamDigest = {
  workstreams: [{
    label: "Demo | project",
    confidence: "high",
    episodeIds: ["episode-001"],
    topics: [{ text: "Implemented *browser* support", evidence: ["episode-001"] }],
    outcomes: [{ text: "Demo ran", strength: "observed", evidence: ["episode-001"] }],
  }],
  unassignedEpisodeIds: [],
};
const provenance: SummaryProvenance = {
  provider: "test",
  model: "gpt-test",
  promptSchema: "daytrace.workstream-prompt.v6",
  inputTokens: 100,
  outputTokens: 20,
  requestCount: 1,
};

describe("AI report rendering", () => {
  it("renders the journal-ready workstream table safely", () => {
    const output = renderDigestMarkdown(bundle, digest, provenance);
    expect(output).toContain("## What this day appears to contain");
    expect(output).toContain("| Project / workstream | Apparent achievements | Work and topics |");
    expect(output).toContain("| **Demo \\| project** | Demo ran | Implemented \\*browser\\* support |");
    expect(output.endsWith("\n")).toBe(true);
  });

  it("renders the stable workstream-report.v2 JSON", () => {
    const output = JSON.parse(renderDigestJson(bundle, digest, provenance, { details: true })) as Record<string, unknown>;
    expect(output.schema).toBe("daytrace.workstream-report.v2");
    expect(output.summary).toEqual({
      input_tokens: 100,
      model: "gpt-test",
      output_tokens: 20,
      prompt_schema: "daytrace.workstream-prompt.v6",
      provider: "test",
      request_count: 1,
    });
    expect((output.workstreams as Array<Record<string, unknown>>)[0]?.active_seconds).toBe(600);
  });
});

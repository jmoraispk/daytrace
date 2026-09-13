import { describe, expect, it } from "vitest";

import type { DaytraceFailure } from "../src/models.js";
import { renderSummaryFailureJson, safeResponseShape } from "../src/summary-diagnostics.js";

describe("summary diagnostics", () => {
  it("extracts response shape without model prose", () => {
    const shape = safeResponseShape({
      workstreams: [{ episode_ids: ["episode-001", "private"], topics: [{ text: "private prose", evidence: ["episode-001"] }], outcomes: [] }],
      unassigned_episode_ids: ["episode-001"],
    }, new Set(["episode-001"]));
    expect(shape).toMatchObject({ known_allocated_ids: ["episode-001"], unknown_id_count: 1, duplicate_id_count: 1 });
    expect(JSON.stringify(shape)).not.toContain("private prose");
  });

  it("renders an allow-listed failure artifact", () => {
    const failure: DaytraceFailure = {
      code: "invalid-schema",
      field: "schema",
      context: {
        provider: "openai",
        model: "gpt-test",
        stage: "chunk",
        callIndex: 1,
        requestCharacterCount: 123,
        itemIds: ["episode-001"],
      },
      responseShape: { workstream_count: 1, known_allocated_ids: ["episode-001"] },
    };
    expect(JSON.parse(renderSummaryFailureJson(failure))).toEqual({
      call_index: 1,
      daytrace_version: "0.4.0",
      item_count: 1,
      item_ids: ["episode-001"],
      model: "gpt-test",
      provider: "openai",
      request_character_count: 123,
      response_shape: { known_allocated_ids: ["episode-001"], workstream_count: 1 },
      schema: "daytrace.ai-failure.v1",
      stage: "chunk",
      validation: { code: "invalid-schema", field: "schema" },
    });
  });

  it("redacts unsafe failure fields and identifiers", () => {
    const output = renderSummaryFailureJson({ code: "PRIVATE MESSAGE", field: "token=abcdefghijkl" });
    expect(output).not.toContain("PRIVATE MESSAGE");
    expect(output).not.toContain("abcdefghijkl");
  });
});

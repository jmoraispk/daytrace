import { describe, expect, it } from "vitest";

import { SummaryValidationError } from "../src/models.js";
import {
  assembleMergedDigest,
  validateDigest,
  validateFinalAllocation,
  validateMerge,
} from "../src/summarize.js";

function validPayload(): Record<string, unknown> {
  return {
    schema: "daytrace.workstream-digest.v2",
    workstreams: [{
      label: "Demo project",
      confidence: "high",
      episode_ids: ["episode-001"],
      topics: [{ text: "Implemented the demo", evidence: ["episode-001"] }],
      outcomes: [{ text: "Demo ran", strength: "observed", evidence: ["episode-001"] }],
    }],
    unassigned_episode_ids: ["episode-002"],
  };
}

function expectFailure(fn: () => unknown, code: string, field: string): void {
  try {
    fn();
    throw new Error("expected validation failure");
  } catch (error) {
    expect(error).toBeInstanceOf(SummaryValidationError);
    expect(error).toMatchObject({ code, field });
  }
}

describe("digest validation", () => {
  it("accepts a complete digest and removes none-strength outcomes", () => {
    const payload = validPayload();
    const stream = (payload.workstreams as Array<Record<string, unknown>>)[0];
    (stream?.outcomes as unknown[]).push({ text: "No claim", strength: "none", evidence: ["episode-001"] });
    const digest = validateDigest(payload, new Set(["episode-001", "episode-002"]));
    expect(digest.workstreams[0]?.outcomes).toHaveLength(1);
    expect(digest.unassignedEpisodeIds).toEqual(["episode-002"]);
  });

  it.each([
    [{ ...validPayload(), schema: "wrong" }, "invalid-schema", "schema"],
    [{ ...validPayload(), extra: true }, "invalid-shape", "response"],
    [(() => { const value = validPayload(); ((value.workstreams as Array<Record<string, unknown>>)[0]?.topics as Array<Record<string, unknown>>)[0]!.evidence = ["episode-999"]; return value; })(), "unknown-ids", "workstreams[0].topics[0].evidence"],
    [(() => { const value = validPayload(); value.unassigned_episode_ids = ["episode-001", "episode-002"]; return value; })(), "invalid-episode-allocation", "episode-allocation"],
    [(() => { const value = validPayload(); (value.workstreams as Array<Record<string, unknown>>)[0]!.confidence = "certain"; return value; })(), "invalid-enum", "workstreams[0].confidence"],
  ])("rejects malformed digest values", (payload, code, field) => {
    expectFailure(() => validateDigest(payload, new Set(["episode-001", "episode-002"])), code, field);
  });

  it("sanitizes generated text before returning it", () => {
    const payload = validPayload();
    (payload.workstreams as Array<Record<string, unknown>>)[0]!.label = "token=abcdefghijkl";
    expect(validateDigest(payload, new Set(["episode-001", "episode-002"])).workstreams[0]?.label).toBe("[redacted-secret]");
  });
});

describe("merge validation", () => {
  it("preserves singletons and merges only named groups", () => {
    const chunks = [
      validateDigest(validPayload(), new Set(["episode-001", "episode-002"])),
      validateDigest({
        schema: "daytrace.workstream-digest.v2",
        workstreams: [{ label: "Demo follow-up", confidence: "medium", episode_ids: ["episode-003"], topics: [], outcomes: [] }],
        unassigned_episode_ids: [],
      }, new Set(["episode-003"])),
    ];
    const provisional = new Map([
      ["provisional-001-001", chunks[0]!.workstreams[0]!],
      ["provisional-002-001", chunks[1]!.workstreams[0]!],
    ]);
    const groups = validateMerge({
      schema: "daytrace.workstream-merge.v1",
      groups: [{ label: "Demo", confidence: "high", provisional_ids: ["provisional-001-001", "provisional-002-001"] }],
    }, new Set(provisional.keys()));
    const digest = assembleMergedDigest(groups, provisional, chunks);
    expect(digest.workstreams.map((item) => item.label)).toEqual(["Demo"]);
    expect(digest.workstreams[0]?.episodeIds).toEqual(["episode-001", "episode-003"]);
    expect(digest.unassignedEpisodeIds).toEqual(["episode-002"]);
  });

  it("rejects duplicate provisional allocation", () => {
    const payload = {
      schema: "daytrace.workstream-merge.v1",
      groups: [
        { label: "A", confidence: "high", provisional_ids: ["provisional-001"] },
        { label: "B", confidence: "low", provisional_ids: ["provisional-001"] },
      ],
    };
    expectFailure(() => validateMerge(payload, new Set(["provisional-001"])), "invalid-provisional-allocation", "provisional-allocation");
  });

  it("validates final global allocation", () => {
    const digest = validateDigest(validPayload(), new Set(["episode-001", "episode-002"]));
    expect(() => validateFinalAllocation(digest, new Set(["episode-001", "episode-002"]))).not.toThrow();
    expectFailure(() => validateFinalAllocation(digest, new Set(["episode-001"])), "invalid-episode-allocation", "episode-allocation");
  });
});

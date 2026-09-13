import { describe, expect, it } from "vitest";

import { compactSessions } from "../src/episode.js";
import {
  buildMergeRequest,
  buildSummaryPlan,
  mergeJsonFormat,
  workstreamJsonFormat,
} from "../src/summarize.js";
import type { WorkstreamDigest } from "../src/models.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

describe("summary planning", () => {
  it("minimizes episodes and reports included categories", () => {
    const bundle = compactSessions(sessionBundle([
      session("session-001", "Demo", [slice(0, 10, {
        title: "Demo repo",
        project: "demo",
        file: "main.ts",
        urlHost: "github.com",
        urlPath: "/octo/demo",
      })]),
    ]));
    const plan = buildSummaryPlan(bundle);
    expect(plan.episodeCount).toBe(1);
    expect(plan.plannedRequestCount).toBe(1);
    expect(plan.dataCategories).toContain("anchor");
    expect(plan.requests[0]?.payload).not.toHaveProperty("sessions");
    expect(JSON.stringify(plan.requests[0]?.payload)).not.toContain("sessions");
  });

  it("chunks only at episode boundaries", () => {
    const bundle = compactSessions(sessionBundle([
      session("session-001", "First", [slice(0, 5, { title: "A".repeat(300) })]),
      session("session-002", "Second", [slice(40, 5, { title: "B".repeat(300), evidenceIds: ["evidence-0002"] })]),
    ]));
    const plan = buildSummaryPlan(bundle, { targetCharacters: 700, maxCharacters: 2_000 });
    expect(plan.requests).toHaveLength(2);
    expect(plan.requests.map((item) => item.episodeIds)).toEqual([
      ["episode-001"],
      ["episode-002"],
    ]);
    expect(plan.plannedRequestCount).toBe(3);
  });

  it("builds stable provisional merge requests and restricted formats", () => {
    const chunks: readonly WorkstreamDigest[] = [{
      workstreams: [{
        label: "Demo",
        confidence: "high",
        episodeIds: ["episode-001"],
        topics: [{ text: "Implemented demo", evidence: ["episode-001"] }],
        outcomes: [],
      }],
      unassignedEpisodeIds: [],
    }];
    const { request, provisional } = buildMergeRequest(chunks);
    expect(request.schema).toBe("daytrace.workstream-merge-request.v1");
    expect(request.provisionalIds).toEqual(["provisional-001-001"]);
    expect(provisional.get("provisional-001-001")?.label).toBe("Demo");
    expect(JSON.stringify(workstreamJsonFormat(["episode-001"]))).toContain("episode-001");
    expect(JSON.stringify(mergeJsonFormat(request.provisionalIds))).toContain("provisional-001-001");
  });

  it("retains strict item schemas for empty request formats", () => {
    const workstream = workstreamJsonFormat([]) as any;
    const merge = mergeJsonFormat([]) as any;
    expect(workstream.schema.properties.workstreams.items.required).toEqual([
      "label", "confidence", "episode_ids", "topics", "outcomes",
    ]);
    expect(workstream.schema.properties.workstreams.maxItems).toBe(0);
    expect(merge.schema.properties.groups.items.required).toEqual([
      "label", "confidence", "provisional_ids",
    ]);
    expect(merge.schema.properties.groups.maxItems).toBe(0);
  });
});

import { describe, expect, it } from "vitest";

import { compactSessions } from "../src/episode.js";
import type { ProviderRequest, ProviderResponse, SummaryProvider } from "../src/models.js";
import {
  buildSummaryPlan,
  summarizeBundle,
  summarizeBundleOrFallback,
} from "../src/summarize.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

function bundle(count = 1) {
  return compactSessions(sessionBundle(Array.from({ length: count }, (_, index) => session(
    `session-${String(index + 1).padStart(3, "0")}`,
    `Project ${index + 1}`,
    [slice(index * 40, 5, { title: `Project ${index + 1}`, evidenceIds: [`evidence-${String(index + 1).padStart(4, "0")}`] })],
  ))));
}

function chunkPayload(ids: readonly string[], allocation = ids): Record<string, unknown> {
  return {
    schema: "daytrace.workstream-digest.v2",
    workstreams: allocation.map((id) => ({
      label: `Work ${id}`,
      confidence: "high",
      episode_ids: [id],
      topics: [{ text: "Implemented work", evidence: [id] }],
      outcomes: [],
    })),
    unassigned_episode_ids: [],
  };
}

class RecordingProvider implements SummaryProvider {
  readonly calls: ProviderRequest[] = [];
  private readonly responses: unknown[];

  constructor(responses: readonly unknown[]) { this.responses = [...responses]; }

  async complete(request: ProviderRequest): Promise<ProviderResponse> {
    this.calls.push(request);
    const payload = this.responses.shift();
    if (payload instanceof Error) throw payload;
    return { payload, provider: "test", model: "gpt-test", inputTokens: 10, outputTokens: 5, responseId: "resp_test" };
  }
}

describe("summary provider orchestration", () => {
  it("summarizes one chunk and aggregates provenance", async () => {
    const input = bundle();
    const provider = new RecordingProvider([chunkPayload(["episode-001"])]);
    const result = await summarizeBundle(input, provider);
    expect(result.digest.workstreams[0]?.label).toBe("Work episode-001");
    expect(result.provenance).toMatchObject({ provider: "test", model: "gpt-test", requestCount: 1, inputTokens: 10, outputTokens: 5 });
    expect(provider.calls[0]).toMatchObject({ passKind: "chunk" });
  });

  it("repairs allocation once and then validates", async () => {
    const input = bundle();
    const provider = new RecordingProvider([
      chunkPayload(["episode-001"], []),
      chunkPayload(["episode-001"]),
    ]);
    const result = await summarizeBundle(input, provider);
    expect(result.provenance.requestCount).toBe(2);
    expect(provider.calls[1]?.payload).toHaveProperty("repair_instruction");
  });

  it("merges multi-chunk summaries while retaining omitted singletons", async () => {
    const input = bundle(2);
    const plan = buildSummaryPlan(input, { targetCharacters: 1, maxCharacters: 100_000 });
    const provider = new RecordingProvider([
      chunkPayload(["episode-001"]),
      chunkPayload(["episode-002"]),
      { schema: "daytrace.workstream-merge.v1", groups: [] },
    ]);
    const result = await summarizeBundle(input, provider, plan);
    expect(provider.calls.map((item) => item.passKind)).toEqual(["chunk", "chunk", "merge"]);
    expect(result.digest.workstreams).toHaveLength(2);
    expect(result.provenance.requestCount).toBe(3);
  });

  it("falls back without retaining arbitrary provider messages", async () => {
    const provider = new RecordingProvider([new Error("private provider message token=abcdefghijkl")]);
    const result = await summarizeBundleOrFallback(bundle(), provider);
    expect(result.kind).toBe("deterministic");
    expect(JSON.stringify(result)).not.toContain("private provider message");
    if (result.kind === "deterministic") expect(result.failure.code).toBe("provider-request");
  });

  it("propagates cancellation instead of falling back", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(summarizeBundleOrFallback(bundle(), new RecordingProvider([]), undefined, { signal: controller.signal })).rejects.toBe(controller.signal.reason);
  });
});

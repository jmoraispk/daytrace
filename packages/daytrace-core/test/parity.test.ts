import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import { collectDay } from "../src/activitywatch.js";
import { renderDigestJson, renderEpisodeJson } from "../src/json-output.js";
import { renderDigestMarkdown, renderEpisodeMarkdown } from "../src/markdown.js";
import type { ActivityWatchTransport, SummaryProvenance } from "../src/models.js";
import { MERGE_SYSTEM_PROMPT, SYSTEM_PROMPT } from "../src/prompts.js";
import { buildSummaryPlan, mergeJsonFormat, validateDigest, workstreamJsonFormat } from "../src/summarize.js";
import { resolveDay } from "../src/time.js";

const FIXTURES = new URL("../../../tests/fixtures/cross-language/", import.meta.url);

async function text(name: string): Promise<string> {
  return readFile(new URL(name, FIXTURES), "utf8");
}

async function json(name: string): Promise<any> {
  return JSON.parse(await text(name));
}

function transport(input: any): ActivityWatchTransport {
  return {
    async request({ path }) {
      if (path === "/api/0/info") return { version: "v0.synthetic", testing: true };
      if (path === "/api/0/buckets") return Object.fromEntries(input.buckets.map((item: any) => [item.id, {
        type: item.type,
        client: item.client,
        hostname: item.hostname,
      }]));
      const bucket = decodeURIComponent(path.split("/").at(-2) ?? "");
      return (input.events[bucket] ?? []).map((item: any) => ({
        id: item.id,
        timestamp: item.timestamp,
        duration: item.duration,
        data: item.data,
      }));
    },
  };
}

describe("Python/TypeScript parity", () => {
  it("matches the synthetic deterministic pipeline and rendering", async () => {
    const input = await json("pipeline-input.json");
    const expected = await json("pipeline-expected.json");
    const bundle = await collectDay({
      day: input.day,
      timezoneName: input.timezone,
      transport: transport(input),
    });
    const actual = JSON.parse(renderEpisodeJson(bundle, { details: true, raw: true }));
    const plan = buildSummaryPlan(bundle);
    actual.summary_plan = {
      episode_count: plan.episodeCount,
      input_character_count: plan.inputCharacterCount,
      planned_request_count: plan.plannedRequestCount,
      data_categories: plan.dataCategories,
      request_episode_ids: plan.requests.map((item) => item.episodeIds),
      request_payloads: plan.requests.map((item) => item.payload),
    };
    expect(actual).toEqual(expected);
    expect(renderEpisodeJson(bundle, { details: true, raw: true })).toBe(await text("episode-json-expected.json"));
    expect(renderEpisodeMarkdown(bundle, { details: true, raw: true })).toBe(await text("episode-expected.md"));
  });

  it("matches validated AI JSON and journal Markdown", async () => {
    const input = await json("pipeline-input.json");
    const bundle = await collectDay({ day: input.day, timezoneName: input.timezone, transport: transport(input) });
    const digestInput = await json("digest-input.json");
    const digest = validateDigest(digestInput.payload, new Set(bundle.episodes.map((item) => item.episodeId)));
    const raw = digestInput.provenance;
    const provenance: SummaryProvenance = {
      provider: raw.provider,
      model: raw.model,
      promptSchema: raw.prompt_schema,
      inputTokens: raw.input_tokens,
      outputTokens: raw.output_tokens,
      requestCount: raw.request_count,
    };
    expect(renderDigestJson(bundle, digest, provenance, { details: true })).toBe(await text("digest-expected.json"));
    expect(renderDigestMarkdown(bundle, digest, provenance, { details: true })).toBe(await text("digest-expected.md"));
  });

  it("matches DST day boundaries", async () => {
    const expected = await json("dst-expected.json");
    for (const day of Object.keys(expected)) {
      const window = resolveDay(day, "America/Los_Angeles");
      expect({
        timezone: window.timezoneName,
        start: window.start,
        end: window.end,
        duration_seconds: (Date.parse(window.end) - Date.parse(window.start)) / 1000,
      }).toEqual(expected[day]);
    }
  });

  it("matches exact prompts and structured response formats", async () => {
    expect({ merge: MERGE_SYSTEM_PROMPT, system: SYSTEM_PROMPT }).toEqual(await json("prompts-expected.json"));
    expect({
      merge: mergeJsonFormat(["provisional-001-001"]),
      merge_empty: mergeJsonFormat([]),
      workstream: workstreamJsonFormat(["episode-001"]),
      workstream_empty: workstreamJsonFormat([]),
    }).toEqual(await json("formats-expected.json"));
  });
});

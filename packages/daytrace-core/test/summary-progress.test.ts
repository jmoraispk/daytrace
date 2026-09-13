import { expect, it } from "vitest";

import { compactSessions } from "../src/episode.js";
import type { ProgressEvent, SummaryProvider } from "../src/models.js";
import { summarizeBundle } from "../src/summarize.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

it("emits content-free summary progress", async () => {
  const input = compactSessions(sessionBundle([session("session-001", "Secret Project", [slice(0, 5)])]));
  const provider: SummaryProvider = {
    async complete() {
      return {
        provider: "test",
        model: "gpt-test",
        payload: {
          schema: "daytrace.workstream-digest.v2",
          workstreams: [{ label: "Result", confidence: "high", episode_ids: ["episode-001"], topics: [], outcomes: [] }],
          unassigned_episode_ids: [],
        },
      };
    },
  };
  const progress: ProgressEvent[] = [];
  await summarizeBundle(input, provider, undefined, { onProgress: (event) => progress.push(event) });
  expect(progress.map((item) => item.stage)).toEqual([
    "summary:chunk",
    "summary:response",
    "summary:validate",
    "complete",
  ]);
  expect(JSON.stringify(progress)).not.toContain("Secret Project");
});

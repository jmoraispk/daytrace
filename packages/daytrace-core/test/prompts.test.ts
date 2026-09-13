import { expect, it } from "vitest";

import { MERGE_SYSTEM_PROMPT, SYSTEM_PROMPT } from "../src/prompts.js";

it("exports the versioned Python summary prompts", () => {
  expect(SYSTEM_PROMPT).toContain("journal-ready account");
  expect(SYSTEM_PROMPT).toMatch(/Partition every\nsupplied episode ID exactly once/);
  expect(SYSTEM_PROMPT.endsWith("Never calculate durations.")).toBe(true);
  expect(MERGE_SYSTEM_PROMPT).toContain("Omit unrelated or singleton provisional");
  expect(MERGE_SYSTEM_PROMPT.endsWith("allocations.")).toBe(true);
});

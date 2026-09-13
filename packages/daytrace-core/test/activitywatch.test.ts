import { describe, expect, it } from "vitest";

import { collectDay } from "../src/activitywatch.js";
import type { ActivityWatchTransport, ProgressEvent } from "../src/models.js";

function syntheticTransport(): ActivityWatchTransport {
  return {
    async request({ path }) {
      if (path === "/api/0/info") return { version: "v0.test", testing: true };
      if (path === "/api/0/buckets") {
        return {
          window: { type: "currentwindow", client: "test", hostname: "test" },
          afk: { type: "afkstatus", client: "test", hostname: "test" },
          ignored: { type: "unsupported", client: "test", hostname: "test" },
        };
      }
      if (path.includes("/window/")) {
        return [{
          id: 1,
          timestamp: "2026-09-10T09:00:00Z",
          duration: 600,
          data: { app: "Code", title: "Synthetic Project" },
        }];
      }
      return [{
        id: 2,
        timestamp: "2026-09-10T09:05:00Z",
        duration: 60,
        data: { status: "afk" },
      }];
    },
  };
}

describe("collectDay", () => {
  it("runs the complete deterministic pipeline through an injected transport", async () => {
    const progress: ProgressEvent[] = [];
    const bundle = await collectDay({
      day: "2026-09-10",
      timezoneName: "UTC",
      server: "http://127.0.0.1:5600",
      transport: syntheticTransport(),
      onProgress: (event) => progress.push(event),
    });

    expect(bundle.episodes).toHaveLength(1);
    expect(bundle.episodes[0]?.activeSeconds).toBe(540);
    expect(bundle.diagnostics).toEqual([{ code: "unsupported-bucket", count: 1 }]);
    expect(progress.map((event) => event.stage)).toEqual([
      "activitywatch:info",
      "activitywatch:buckets",
      "activitywatch:events",
      "pipeline:normalize",
      "pipeline:sanitize",
      "pipeline:fuse",
      "pipeline:sessions",
      "pipeline:episodes",
      "complete",
    ]);
    expect(JSON.stringify(progress)).not.toContain("Synthetic Project");
    expect(progress.every((event) => Number.isInteger(event.elapsedSeconds))).toBe(true);
  });

  it("propagates cancellation without making another transport request", async () => {
    const controller = new AbortController();
    let calls = 0;
    const transport: ActivityWatchTransport = {
      async request() {
        calls += 1;
        controller.abort();
        return { version: "v0.test", testing: true };
      },
    };

    await expect(collectDay({
      day: "2026-09-10",
      timezoneName: "UTC",
      transport,
      signal: controller.signal,
    })).rejects.toMatchObject({ name: "AbortError" });
    expect(calls).toBe(1);
  });
});

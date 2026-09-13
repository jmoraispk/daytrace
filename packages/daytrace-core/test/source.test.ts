import { describe, expect, it } from "vitest";

import { ActivityWatchSource, parseServerUrl } from "../src/source.js";
import type { ActivityWatchRequest, ActivityWatchTransport } from "../src/models.js";

describe("ActivityWatch source", () => {
  it("parses a root server URL and applies the default port", () => {
    expect(parseServerUrl("http://127.0.0.1")).toEqual({
      protocol: "http",
      host: "127.0.0.1",
      port: 5600,
    });
  });

  it.each([
    "ftp://127.0.0.1:5600",
    "http://user:secret@127.0.0.1:5600",
    "http://127.0.0.1:5600/api",
    "http://127.0.0.1:5600?x=1",
    "http://127.0.0.1:not-a-port",
  ])("rejects ambiguous URLs without echoing them: %s", (server) => {
    expect(() => parseServerUrl(server)).toThrow("invalid ActivityWatch server URL");
  });

  it("converts injected transport responses", async () => {
    const calls: ActivityWatchRequest[] = [];
    const transport: ActivityWatchTransport = {
      async request(input) {
        calls.push(input);
        if (input.path === "/api/0/info") return { version: "v0.test", testing: true };
        if (input.path === "/api/0/buckets") {
          return {
            "window-test": {
              type: "currentwindow",
              client: "aw-watcher-window",
              hostname: "test",
            },
          };
        }
        return [{ id: 7, timestamp: "2026-09-10T16:00:00Z", duration: 300, data: { app: "Code" } }];
      },
    };
    const source = new ActivityWatchSource("http://127.0.0.1:5600", transport);

    expect(await source.getInfo()).toEqual({ version: "v0.test", testing: true });
    expect(await source.listBuckets()).toEqual([
      { id: "window-test", type: "currentwindow", client: "aw-watcher-window", hostname: "test" },
    ]);
    expect(await source.getEvents("window-test", "2026-09-10T00:00:00.000Z", "2026-09-11T00:00:00.000Z"))
      .toEqual([{ id: "7", timestamp: "2026-09-10T16:00:00Z", durationSeconds: 300, data: { app: "Code" } }]);
    expect(calls[2]?.path).toBe("/api/0/buckets/window-test/events");
  });
});

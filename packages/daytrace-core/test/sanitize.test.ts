import { describe, expect, it } from "vitest";

import { sanitizeGeneratedText, sanitizeRecords } from "../src/sanitize.js";
import type { ActivityRecord, DiagnosticCode } from "../src/models.js";

const base: ActivityRecord = {
  eventId: "1",
  bucketId: "window",
  kind: "current-window",
  start: "2026-09-10T09:00:00.000Z",
  end: "2026-09-10T09:01:00.000Z",
};

describe("sanitization", () => {
  it("redacts URL tokens, email, secrets, and Edge suffixes", () => {
    const diagnostics: DiagnosticCode[] = [];
    const result = sanitizeRecords([
      { ...base, title: "https://login.example/callback?code=oauth-secret", urlHost: "login.example", urlPath: "/callback" },
      { ...base, eventId: "2", title: "Inbox - person@example.test - Outlook" },
      { ...base, eventId: "3", title: "PerfLife and 45 more pages - Work - Microsoft Edge" },
      { ...base, eventId: "4", title: "token=abcdefghijklmnop" },
    ], (code) => diagnostics.push(code));

    expect(result.map((item) => item.title)).toEqual([
      "login.example",
      "Inbox - [redacted-email] - Outlook",
      "PerfLife",
      "[redacted-secret]",
    ]);
    expect(result[0]?.urlPath).toBeUndefined();
    expect(diagnostics.length).toBeGreaterThan(0);
  });

  it("minimizes paths and keeps bounded repository paths", () => {
    const result = sanitizeRecords([
      { ...base, kind: "editor", project: "C:\\Users\\example\\demo", file: "C:\\Users\\example\\demo\\main.ts" },
      { ...base, eventId: "2", kind: "browser", urlHost: "github.com", urlPath: "/octo/demo/issues/1/private" },
      { ...base, eventId: "3", kind: "browser", urlHost: "gitlab.example", urlPath: "/team/demo/-/merge_requests/15/diffs" },
    ], () => undefined);

    expect(result[0]?.project).toBe("demo");
    expect(result[0]?.file).toBe("main.ts");
    expect(result[1]?.urlPath).toBe("/octo/demo");
    expect(result[2]?.urlPath).toBe("/team/demo/-/merge_requests/15");
  });

  it.each([
    "code_challenge=abcdefghijklmnop",
    "session_state=abcdefghijklmnop",
    "api_key=abcdefghijklmnop",
    "Open http://127.0.0.1:9000/?key=eeeeeeeeeeeeeeee",
  ])("scans generated text before truncation", (value) => {
    expect(sanitizeGeneratedText(value)).not.toMatch(/abcdefghijklmnop|eeeeeeee/);
  });
});

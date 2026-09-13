import { describe, expect, it } from "vitest";

import {
  assertCloudSafePayload,
  minimizeCloudPath,
  minimizeCloudText,
  minimizeCloudTitle,
} from "../src/cloud-privacy.js";
import { CloudPrivacyError } from "../src/models.js";

describe("cloud privacy", () => {
  it("minimizes communications and paths", () => {
    expect(minimizeCloudTitle("Slack", "Alex (DM) - Slack")).toBe("Direct message - Slack");
    expect(minimizeCloudTitle("Teams", "Private standup notes")).toBe("Meeting - Microsoft Teams");
    expect(minimizeCloudTitle("Outlook", "Inbox - alex@example.test")).toBe("Inbox - Outlook");
    expect(minimizeCloudPath("C:\\Users\\Example\\demo.ts")).toBe("demo.ts");
    expect(minimizeCloudText(" token=abcdefghijkl ")).toBe("[redacted-secret]");
  });

  it("rejects unsafe strings at any payload depth", () => {
    expect(() => assertCloudSafePayload({ nested: ["token=abcdefghijkl"] })).toThrow(CloudPrivacyError);
    expect(() => assertCloudSafePayload({ nested: ["safe"] })).not.toThrow();
  });
});

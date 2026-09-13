import { describe, expect, it } from "vitest";

import { compactSessions } from "../src/episode.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

function repositorySession(id: string, start: number, repository: string) {
  return session(id, repository, [slice(start, 1, {
    title: repository,
    urlHost: "github.com",
    urlPath: `/octo/${repository}`,
    evidenceIds: [`evidence-${id}`],
  })]);
}

function genericSession(id: string, start: number) {
  return session(id, "ChatGPT", [slice(start, 1, {
    app: "ChatGPT",
    title: "ChatGPT",
    evidenceIds: [`evidence-${id}`],
  })]);
}

describe("compactSessions", () => {
  it("bridges generic activity between compatible repositories", () => {
    const result = compactSessions(sessionBundle([
      repositorySession("session-001", 0, "alpha"),
      genericSession("session-002", 2),
      repositorySession("session-003", 5, "alpha"),
    ]));

    expect(result.episodes).toHaveLength(1);
    expect(result.episodes[0]?.sessionIds).toEqual(["session-001", "session-002", "session-003"]);
  });

  it("does not bridge incompatible repositories", () => {
    const result = compactSessions(sessionBundle([
      repositorySession("session-001", 0, "alpha"),
      genericSession("session-002", 2),
      repositorySession("session-003", 5, "beta"),
    ]));

    expect(result.episodes.map((item) => item.sessionIds)).toEqual([
      ["session-001"],
      ["session-002"],
      ["session-003"],
    ]);
  });

  it("conserves membership and fractional active duration", () => {
    const bundle = sessionBundle([
      { ...repositorySession("session-001", 0, "alpha"), activeSeconds: 0.1, focusedSeconds: 0.1 },
      { ...repositorySession("session-002", 10, "beta"), activeSeconds: 0.1, focusedSeconds: 0.1 },
      { ...repositorySession("session-003", 11, "beta"), activeSeconds: 1.1, focusedSeconds: 1.1 },
    ]);
    const result = compactSessions(bundle);

    expect(result.episodes.reduce((sum, item) => sum + item.activeSeconds, 0))
      .toBeCloseTo(result.sessions.reduce((sum, item) => sum + item.activeSeconds, 0), 12);
    expect(result.episodes.flatMap((item) => item.sessionIds).sort())
      .toEqual(result.sessions.map((item) => item.sessionId).sort());
  });
});

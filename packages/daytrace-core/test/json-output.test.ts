import { describe, expect, it } from "vitest";

import { renderEpisodeJson, renderSessionJson } from "../src/json-output.js";
import { compactSessions } from "../src/episode.js";
import { session, sessionBundle, slice } from "./pipeline-factories.js";

const sessions = sessionBundle([
  session("session-001", "octo/demo", [slice(0, 10, { title: "Demo", urlPath: "/octo/demo" })]),
]);
const episodes = compactSessions(sessions);

describe("deterministic JSON", () => {
  it("uses stable versioned episode output", () => {
    const rendered = renderEpisodeJson(episodes);
    const payload = JSON.parse(rendered) as Record<string, unknown>;

    expect(payload.schema).toBe("daytrace.episode-bundle.v1");
    expect((payload.episodes as Array<{ id: string }>)[0]?.id).toBe("episode-001");
    expect(payload.sessions).toBeUndefined();
    expect(rendered.endsWith("\n")).toBe(true);
    expect(rendered.indexOf('"date"')).toBeLessThan(rendered.indexOf('"episodes"'));
  });

  it("includes fine-grained sessions only when requested", () => {
    const episodePayload = JSON.parse(renderEpisodeJson(episodes, { raw: true })) as Record<string, unknown>;
    const sessionPayload = JSON.parse(renderSessionJson(sessions, { details: true })) as Record<string, unknown>;
    expect((episodePayload.sessions as Array<{ id: string }>)[0]?.id).toBe("session-001");
    expect((sessionPayload.sessions as Array<{ evidence_ids: string[] }>)[0]?.evidence_ids).toEqual(["evidence-0001"]);
  });
});

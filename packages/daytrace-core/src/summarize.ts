import { minimizeCloudText, minimizeCloudTitle } from "./cloud-privacy.js";
import { compactSessions } from "./episode.js";
import type {
  ActivityEpisode,
  EpisodeBundle,
  JsonObject,
  JsonValue,
  MergeRequest,
  SessionBundle,
  SummaryPlan,
  SummaryRequest,
  WorkstreamDigest,
  WorkstreamSummary,
} from "./models.js";
import { DaytraceError } from "./models.js";

export const PROMPT_SCHEMA = "daytrace.workstream-prompt.v6";
export const REQUEST_SCHEMA = "daytrace.summary-request.v2";
export const DIGEST_SCHEMA = "daytrace.workstream-digest.v2";
export const MAX_REQUEST_CHARACTERS = 100_000;
export const TARGET_REQUEST_CHARACTERS = 80_000;
export const ALLOCATION_REPAIR_INSTRUCTION = "Partition every supplied episode ID exactly once across workstreams[].episode_ids and unassigned_episode_ids.";
const CATEGORY_ORDER = ["anchor", "application", "activity-label", "outcome-signal"] as const;

export class SummaryRequestTooLarge extends DaytraceError {
  constructor(code = "summary-request-too-large") { super(code, "summary request is too large"); }
}
export class EpisodeRequestTooLarge extends SummaryRequestTooLarge {
  constructor() { super("episode-request-too-large"); }
}
export class MergeRequestTooLarge extends SummaryRequestTooLarge {
  constructor() { super("merge-request-too-large"); }
}

function pythonJson(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "null";
  if (Array.isArray(value)) return `[${value.map(pythonJson).join(", ")}]`;
  if (typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}: ${pythonJson(item)}`).join(", ")}}`;
  }
  throw new TypeError("unsupported JSON value");
}

function characterCount(value: unknown): number {
  return [...pythonJson(value)].length;
}

function uniqueObjects(values: readonly JsonObject[]): readonly JsonObject[] {
  const seen = new Set<string>();
  return values.filter((item) => {
    const marker = pythonJson(item);
    if (Object.keys(item).length === 0 || seen.has(marker)) return false;
    seen.add(marker);
    return true;
  });
}

function episodePayload(episode: ActivityEpisode, categories: Set<string>): JsonObject {
  const anchors = uniqueObjects(episode.anchors.map((item) => ({
    kind: item.kind,
    value: (item.kind === "title" ? minimizeCloudTitle(undefined, item.value) : minimizeCloudText(item.value)) ?? null,
  })));
  const applications = uniqueObjects(episode.applications.map((item) => ({ value: minimizeCloudText(item.value) ?? null, count: item.count })));
  const activityLabels = uniqueObjects(episode.activityLabels.map((item) => ({ value: minimizeCloudTitle(undefined, item.value) ?? null, count: item.count })));
  const outcomeSignals = uniqueObjects(episode.outcomeSignals.map((item) => ({ code: item.code, label: minimizeCloudText(item.label) ?? null })));
  for (const [values, category] of [
    [anchors, "anchor"],
    [applications, "application"],
    [activityLabels, "activity-label"],
    [outcomeSignals, "outcome-signal"],
  ] as const) if (values.length > 0) categories.add(category);
  return {
    id: episode.episodeId,
    start: episode.start,
    end: episode.end,
    active_seconds: episode.activeSeconds,
    ...(episode.focusedSeconds === undefined ? {} : { focused_seconds: episode.focusedSeconds }),
    label: minimizeCloudTitle(undefined, episode.label) ?? null,
    anchors,
    applications,
    activity_labels: activityLabels,
    transition_count: episode.sessionIds.length,
    outcome_signals: outcomeSignals,
  };
}

function requestForEpisodes(bundle: EpisodeBundle, episodes: readonly ActivityEpisode[]): SummaryRequest {
  const categories = new Set<string>();
  const payload: JsonObject = {
    schema: REQUEST_SCHEMA,
    prompt_schema: PROMPT_SCHEMA,
    date: bundle.day,
    timezone: bundle.timezoneName,
    ...(bundle.focusedSeconds === undefined ? {} : { focused_seconds: bundle.focusedSeconds }),
    episodes: episodes.map((item) => episodePayload(item, categories)),
  };
  return {
    schema: REQUEST_SCHEMA,
    passKind: "chunk",
    payload,
    characterCount: characterCount(payload),
    episodeIds: episodes.map((item) => item.episodeId),
    dataCategories: CATEGORY_ORDER.filter((item) => categories.has(item)),
  };
}

function episodeBundle(bundle: EpisodeBundle | SessionBundle): EpisodeBundle {
  return "episodes" in bundle ? bundle : compactSessions(bundle);
}

export interface SummaryPlanOptions {
  readonly targetCharacters?: number;
  readonly maxCharacters?: number;
}

export function buildSummaryPlan(bundle: EpisodeBundle | SessionBundle, options: SummaryPlanOptions = {}): SummaryPlan {
  const resolved = episodeBundle(bundle);
  const target = options.targetCharacters ?? TARGET_REQUEST_CHARACTERS;
  const maximum = options.maxCharacters ?? MAX_REQUEST_CHARACTERS;
  const groups: ActivityEpisode[][] = [];
  let current: ActivityEpisode[] = [];
  for (const episode of resolved.episodes) {
    const candidate = [...current, episode];
    if (current.length > 0 && requestForEpisodes(resolved, candidate).characterCount > target) {
      groups.push(current);
      current = [episode];
    } else current.push(episode);
    if (requestForEpisodes(resolved, current).characterCount > maximum) throw new EpisodeRequestTooLarge();
  }
  if (current.length > 0 || groups.length === 0) groups.push(current);
  const requests = groups.map((items) => requestForEpisodes(resolved, items));
  if (requests.some((item) => item.characterCount > maximum)) throw new EpisodeRequestTooLarge();
  const dataCategories = CATEGORY_ORDER.filter((category) => requests.some((item) => item.dataCategories.includes(category)));
  return {
    requests,
    episodeCount: resolved.episodes.length,
    inputCharacterCount: requests.reduce((total, item) => total + item.characterCount, 0),
    plannedRequestCount: requests.length + (requests.length > 1 ? 1 : 0),
    dataCategories,
  };
}

export function buildSummaryRequest(bundle: EpisodeBundle | SessionBundle): SummaryRequest {
  const request = buildSummaryPlan(bundle).requests[0];
  if (request === undefined) throw new EpisodeRequestTooLarge();
  return request;
}

function idArraySchema(ids: readonly string[], nonempty: boolean): JsonObject {
  return {
    type: "array",
    ...(nonempty ? { minItems: 1 } : {}),
    items: { type: "string", maxLength: 50, ...(ids.length > 0 ? { enum: ids } : {}) },
  };
}

export function workstreamJsonFormat(episodeIds: readonly string[]): JsonObject {
  const evidence = () => idArraySchema(episodeIds, true);
  const workstreams: JsonObject = episodeIds.length === 0 ? {
    type: "array", maxItems: 0, items: { type: "object" },
  } : {
    type: "array", maxItems: 30,
    items: {
      type: "object", additionalProperties: false,
      required: ["label", "confidence", "episode_ids", "topics", "outcomes"],
      properties: {
        label: { type: "string", maxLength: 120 },
        confidence: { type: "string", enum: ["high", "medium", "low"] },
        episode_ids: idArraySchema(episodeIds, true),
        topics: { type: "array", maxItems: 20, items: { type: "object", additionalProperties: false, required: ["text", "evidence"], properties: { text: { type: "string", maxLength: 500 }, evidence: evidence() } } },
        outcomes: { type: "array", maxItems: 20, items: { type: "object", additionalProperties: false, required: ["text", "strength", "evidence"], properties: { text: { type: "string", maxLength: 500 }, strength: { type: "string", enum: ["observed", "likely", "none"] }, evidence: evidence() } } },
      },
    },
  };
  return {
    type: "json_schema", name: "daytrace_workstream_digest_v2", strict: true,
    schema: {
      type: "object", additionalProperties: false,
      required: ["schema", "workstreams", "unassigned_episode_ids"],
      properties: {
        schema: { type: "string", const: DIGEST_SCHEMA },
        workstreams,
        unassigned_episode_ids: episodeIds.length === 0 ? { type: "array", maxItems: 0, items: { type: "string", maxLength: 50 } } : idArraySchema(episodeIds, false),
      },
    },
  };
}

export function mergeJsonFormat(provisionalIds: readonly string[]): JsonObject {
  return {
    type: "json_schema", name: "daytrace_workstream_merge_v1", strict: true,
    schema: {
      type: "object", additionalProperties: false,
      required: ["schema", "groups"],
      properties: {
        schema: { type: "string", const: "daytrace.workstream-merge.v1" },
        groups: provisionalIds.length === 0 ? { type: "array", maxItems: 0, items: { type: "object" } } : {
          type: "array", maxItems: 30,
          items: { type: "object", additionalProperties: false, required: ["label", "confidence", "provisional_ids"], properties: {
            label: { type: "string", maxLength: 120 },
            confidence: { type: "string", enum: ["high", "medium", "low"] },
            provisional_ids: idArraySchema(provisionalIds, true),
          } },
        },
      },
    },
  };
}

export function buildMergeRequest(
  digests: readonly WorkstreamDigest[],
  options: { readonly maxCharacters?: number } = {},
): { readonly request: MergeRequest; readonly provisional: ReadonlyMap<string, WorkstreamSummary> } {
  const provisional = new Map<string, WorkstreamSummary>();
  const items: JsonObject[] = [];
  digests.forEach((digest, chunkIndex) => digest.workstreams.forEach((workstream, streamIndex) => {
    const id = `provisional-${String(chunkIndex + 1).padStart(3, "0")}-${String(streamIndex + 1).padStart(3, "0")}`;
    provisional.set(id, workstream);
    items.push({
      id,
      label: workstream.label,
      confidence: workstream.confidence,
      episode_ids: workstream.episodeIds,
      topics: workstream.topics.map((item) => ({ text: item.text, evidence: item.evidence })),
      outcomes: workstream.outcomes.map((item) => ({ text: item.text, strength: item.strength, evidence: item.evidence })),
    });
  }));
  const payload: JsonObject = { schema: "daytrace.workstream-merge-request.v1", provisional_workstreams: items };
  const count = characterCount(payload);
  if (count > (options.maxCharacters ?? MAX_REQUEST_CHARACTERS)) throw new MergeRequestTooLarge();
  return {
    request: {
      schema: "daytrace.workstream-merge-request.v1",
      passKind: "merge",
      payload,
      characterCount: count,
      provisionalIds: [...provisional.keys()],
    },
    provisional,
  };
}

export const __private = { pythonJson, characterCount };

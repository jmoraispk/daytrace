import { minimizeCloudText, minimizeCloudTitle } from "./cloud-privacy.js";
import { compactSessions } from "./episode.js";
import type {
  ActivityEpisode,
  EpisodeBundle,
  JsonObject,
  JsonValue,
  MergeGroup,
  MergeRequest,
  SessionBundle,
  SummaryPlan,
  SummaryRequest,
  WorkstreamDigest,
  WorkstreamSummary,
} from "./models.js";
import { DaytraceError, SummaryValidationError } from "./models.js";
import { sanitizeGeneratedText } from "./sanitize.js";

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

function fail(code: string, field: string): never {
  throw new SummaryValidationError(code, field);
}

function boundedText(value: unknown, field: string, limit = 500): string {
  if (typeof value !== "string" || value.trim().length === 0 || [...value].length > limit) fail("invalid-text", field);
  return sanitizeGeneratedText(value.trim());
}

function plainObject(value: unknown, field: string, required: ReadonlySet<string>): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail("invalid-shape", field);
  const prototype = Object.getPrototypeOf(value) as unknown;
  if (prototype !== Object.prototype && prototype !== null) fail("invalid-shape", field);
  const result = value as Record<string, unknown>;
  const keys = Object.keys(result);
  if (keys.length !== required.size || keys.some((key) => !required.has(key))) fail("invalid-shape", field);
  return result;
}

function boundedList(value: unknown, field: string, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) fail("invalid-shape", field);
  return value;
}

function evidenceIds(value: unknown, allowed: ReadonlySet<string>, field: string): readonly string[] {
  const items = boundedList(value, field, 100);
  if (items.length === 0) fail("empty-evidence", field);
  const result = items.map((item) => boundedText(item, field, 50));
  if (new Set(result).size !== result.length) fail("duplicate-ids", field);
  if (result.some((item) => !allowed.has(item))) fail("unknown-ids", field);
  return result;
}

function requiredIds(value: unknown, allowed: ReadonlySet<string>, field: string): readonly string[] {
  const items = boundedList(value, field, 100);
  const result = items.map((item) => boundedText(item, field, 50));
  if (result.length === 0) fail("empty-ids", field);
  if (new Set(result).size !== result.length) fail("duplicate-ids", field);
  if (result.some((item) => !allowed.has(item))) fail("unknown-ids", field);
  return result;
}

const CONFIDENCE = new Set(["high", "medium", "low"] as const);
const STRENGTH = new Set(["observed", "likely", "none"] as const);

export function validateDigest(payload: unknown, allowedEpisodeIds: ReadonlySet<string>): WorkstreamDigest {
  const root = plainObject(payload, "response", new Set(["schema", "workstreams", "unassigned_episode_ids"]));
  if (root.schema !== DIGEST_SCHEMA) fail("invalid-schema", "schema");
  const workstreams: WorkstreamSummary[] = [];
  const allocated: string[] = [];
  for (const [index, raw] of boundedList(root.workstreams, "workstreams", 30).entries()) {
    const field = `workstreams[${index}]`;
    const value = plainObject(raw, field, new Set(["label", "confidence", "episode_ids", "topics", "outcomes"]));
    const episodeIds = requiredIds(value.episode_ids, allowedEpisodeIds, `${field}.episode_ids`);
    allocated.push(...episodeIds);
    const confidence = boundedText(value.confidence, `${field}.confidence`, 20);
    if (!CONFIDENCE.has(confidence as "high" | "medium" | "low")) fail("invalid-enum", `${field}.confidence`);
    const topics = boundedList(value.topics, `${field}.topics`, 20).map((rawTopic, topicIndex) => {
      const topicField = `${field}.topics[${topicIndex}]`;
      const topic = plainObject(rawTopic, topicField, new Set(["text", "evidence"]));
      return {
        text: boundedText(topic.text, `${topicField}.text`),
        evidence: evidenceIds(topic.evidence, allowedEpisodeIds, `${topicField}.evidence`),
      };
    });
    const outcomes = boundedList(value.outcomes, `${field}.outcomes`, 20).flatMap((rawOutcome, outcomeIndex) => {
      const outcomeField = `${field}.outcomes[${outcomeIndex}]`;
      const outcome = plainObject(rawOutcome, outcomeField, new Set(["text", "strength", "evidence"]));
      const strength = boundedText(outcome.strength, `${outcomeField}.strength`, 20);
      if (!STRENGTH.has(strength as "observed" | "likely" | "none")) fail("invalid-enum", `${outcomeField}.strength`);
      const evidence = evidenceIds(outcome.evidence, allowedEpisodeIds, `${outcomeField}.evidence`);
      if (strength === "none") return [];
      return [{
        text: boundedText(outcome.text, `${outcomeField}.text`),
        strength: strength as "observed" | "likely",
        evidence,
      }];
    });
    workstreams.push({
      label: boundedText(value.label, `${field}.label`, 120),
      confidence: confidence as "high" | "medium" | "low",
      episodeIds,
      topics,
      outcomes,
    });
  }
  const unassigned = boundedList(root.unassigned_episode_ids, "unassigned_episode_ids", 100)
    .map((item) => boundedText(item, "unassigned_episode_ids", 50));
  const allocation = [...allocated, ...unassigned];
  if (
    new Set(allocation).size !== allocation.length
    || allocation.some((item) => !allowedEpisodeIds.has(item))
    || allowedEpisodeIds.size !== new Set(allocation).size
  ) fail("invalid-episode-allocation", "episode-allocation");
  return { workstreams, unassignedEpisodeIds: unassigned };
}

export function validateMerge(payload: unknown, allowed: ReadonlySet<string>): readonly MergeGroup[] {
  const root = plainObject(payload, "merge response", new Set(["schema", "groups"]));
  if (root.schema !== "daytrace.workstream-merge.v1") fail("invalid-schema", "schema");
  const allocated: string[] = [];
  const groups = boundedList(root.groups, "groups", 30).map((raw, index) => {
    const field = `groups[${index}]`;
    const value = plainObject(raw, field, new Set(["label", "confidence", "provisional_ids"]));
    const provisionalIds = requiredIds(value.provisional_ids, allowed, `${field}.provisional_ids`);
    allocated.push(...provisionalIds);
    const confidence = boundedText(value.confidence, `${field}.confidence`, 20);
    if (!CONFIDENCE.has(confidence as "high" | "medium" | "low")) fail("invalid-enum", `${field}.confidence`);
    return {
      label: boundedText(value.label, `${field}.label`, 120),
      confidence: confidence as "high" | "medium" | "low",
      provisionalIds,
    };
  });
  if (new Set(allocated).size !== allocated.length) fail("invalid-provisional-allocation", "provisional-allocation");
  return groups;
}

function uniqueByValue<T>(values: readonly T[]): readonly T[] {
  const seen = new Set<string>();
  return values.filter((item) => {
    const marker = pythonJson(item);
    if (seen.has(marker)) return false;
    seen.add(marker);
    return true;
  });
}

export function assembleMergedDigest(
  groups: readonly MergeGroup[],
  provisional: ReadonlyMap<string, WorkstreamSummary>,
  chunks: readonly WorkstreamDigest[],
): WorkstreamDigest {
  const merged = groups.map((group) => {
    const selected = group.provisionalIds.map((id) => provisional.get(id)!);
    return {
      label: group.label,
      confidence: group.confidence,
      episodeIds: selected.flatMap((item) => item.episodeIds),
      topics: uniqueByValue(selected.flatMap((item) => item.topics)),
      outcomes: uniqueByValue(selected.flatMap((item) => item.outcomes)),
    } satisfies WorkstreamSummary;
  });
  const groupIndex = new Map(groups.flatMap((group, index) => group.provisionalIds.map((id) => [id, index] as const)));
  const emitted = new Set<number>();
  const workstreams: WorkstreamSummary[] = [];
  for (const [id, workstream] of provisional) {
    const index = groupIndex.get(id);
    if (index === undefined) workstreams.push(workstream);
    else if (!emitted.has(index)) {
      workstreams.push(merged[index]!);
      emitted.add(index);
    }
  }
  return {
    workstreams,
    unassignedEpisodeIds: uniqueByValue(chunks.flatMap((item) => item.unassignedEpisodeIds)),
  };
}

export function validateFinalAllocation(digest: WorkstreamDigest, allowed: ReadonlySet<string>): void {
  const allocation = [...digest.workstreams.flatMap((item) => item.episodeIds), ...digest.unassignedEpisodeIds];
  if (new Set(allocation).size !== allocation.length || allocation.some((item) => !allowed.has(item)) || allowed.size !== new Set(allocation).size) {
    fail("invalid-episode-allocation", "episode-allocation");
  }
}

export const __private = { pythonJson, characterCount };

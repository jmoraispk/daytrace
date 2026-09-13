import { stableJson } from "./json-output.js";
import type { DaytraceFailure, JsonValue } from "./models.js";
import { DAYTRACE_VERSION } from "./version.js";

const SAFE_IDENTIFIER = /^[A-Za-z0-9._:-]{1,200}$/;
const SAFE_CODE = /^[a-z0-9-]{1,80}$/;
const SAFE_FIELD = /^[A-Za-z0-9_.\[\]-]{1,240}$/;
const SHAPE_LIST_FIELDS = new Set(["known_allocated_ids", "known_unassigned_ids", "known_evidence_ids", "known_provisional_ids"]);
const SHAPE_COUNT_FIELDS = new Set(["workstream_count", "topic_count", "outcome_count", "group_count", "unknown_id_count", "duplicate_id_count"]);

function items(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function safeIdentifier(value: unknown, fallback: string): string {
  return typeof value === "string" && SAFE_IDENTIFIER.test(value) ? value : fallback;
}

export function safeResponseShape(payload: unknown, allowedIds: ReadonlySet<string>): Readonly<Record<string, JsonValue>> {
  const root = typeof payload === "object" && payload !== null && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : {};
  const allocated: string[] = [];
  const unassigned: string[] = [];
  const evidence: string[] = [];
  const provisional: string[] = [];
  let unknownIdCount = 0;
  const collect = (value: unknown, destination: string[]): void => {
    for (const item of items(value)) {
      if (typeof item === "string" && allowedIds.has(item)) destination.push(item);
      else unknownIdCount += 1;
    }
  };
  const workstreams = items(root.workstreams);
  const groups = items(root.groups);
  let topicCount = 0;
  let outcomeCount = 0;
  for (const raw of workstreams) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) continue;
    const stream = raw as Record<string, unknown>;
    collect(stream.episode_ids, allocated);
    const topics = items(stream.topics);
    const outcomes = items(stream.outcomes);
    topicCount += topics.length;
    outcomeCount += outcomes.length;
    for (const item of topics) if (typeof item === "object" && item !== null && !Array.isArray(item)) collect((item as Record<string, unknown>).evidence, evidence);
    for (const item of outcomes) if (typeof item === "object" && item !== null && !Array.isArray(item)) collect((item as Record<string, unknown>).evidence, evidence);
  }
  collect(root.unassigned_episode_ids, unassigned);
  for (const raw of groups) if (typeof raw === "object" && raw !== null && !Array.isArray(raw)) collect((raw as Record<string, unknown>).provisional_ids, provisional);
  const duplicateIdCount = [[...allocated, ...unassigned], evidence, provisional]
    .reduce((total, values) => total + values.length - new Set(values).size, 0);
  return {
    workstream_count: workstreams.length,
    topic_count: topicCount,
    outcome_count: outcomeCount,
    group_count: groups.length,
    known_allocated_ids: [...new Set(allocated)].sort(),
    known_unassigned_ids: [...new Set(unassigned)].sort(),
    known_evidence_ids: [...new Set(evidence)].sort(),
    known_provisional_ids: [...new Set(provisional)].sort(),
    unknown_id_count: unknownIdCount,
    duplicate_id_count: duplicateIdCount,
  };
}

function safeShape(value: Readonly<Record<string, JsonValue>> | undefined): Record<string, JsonValue> {
  if (value === undefined) return {};
  const result: Record<string, JsonValue> = {};
  for (const key of SHAPE_COUNT_FIELDS) {
    const item = value[key];
    if (typeof item === "number" && Number.isInteger(item) && item >= 0) result[key] = item;
  }
  for (const key of SHAPE_LIST_FIELDS) {
    const item = value[key];
    if (Array.isArray(item)) result[key] = item.filter((candidate): candidate is string => typeof candidate === "string" && SAFE_IDENTIFIER.test(candidate));
  }
  return result;
}

export function renderSummaryFailureJson(failure: DaytraceFailure): string {
  const context = failure.context;
  const validation: Record<string, JsonValue> = {
    code: SAFE_CODE.test(failure.code) ? failure.code : "redacted-code",
  };
  if (failure.field !== undefined && SAFE_FIELD.test(failure.field)) validation.field = failure.field;
  const payload: Record<string, JsonValue> = {
    schema: "daytrace.ai-failure.v1",
    daytrace_version: DAYTRACE_VERSION,
    provider: safeIdentifier(context?.provider, "[redacted-provider]"),
    model: safeIdentifier(context?.model, "[redacted-model]"),
    validation,
    response_shape: safeShape(failure.responseShape),
  };
  if (context !== undefined) {
    payload.stage = context.stage;
    payload.call_index = context.callIndex;
    payload.request_character_count = context.requestCharacterCount;
    payload.item_count = context.itemIds.length;
    payload.item_ids = context.itemIds.map((item) => safeIdentifier(item, "[redacted-item]"));
    if (context.responseId !== undefined) payload.response_id = safeIdentifier(context.responseId, "[redacted-response]");
    if (context.requestId !== undefined) payload.request_id = safeIdentifier(context.requestId, "[redacted-request]");
  }
  return stableJson(payload);
}

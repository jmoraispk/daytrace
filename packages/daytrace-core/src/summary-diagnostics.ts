import type { JsonValue } from "./models.js";

const SAFE_IDENTIFIER = /^[A-Za-z0-9._:-]{1,200}$/;

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

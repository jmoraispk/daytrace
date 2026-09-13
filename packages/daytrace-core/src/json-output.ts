import type {
  ActivityEpisode,
  ActivitySession,
  ActivitySlice,
  ContextSignal,
  EpisodeBundle,
  JsonValue,
  SessionBundle,
  SummaryProvenance,
  WorkstreamDigest,
} from "./models.js";
import { durationSeconds, timestampMs } from "./time.js";

export interface EpisodeJsonOptions {
  readonly details?: boolean;
  readonly raw?: boolean;
}

export interface SessionJsonOptions {
  readonly details?: boolean;
}

function pythonIsoTimestamp(value: string): string {
  const date = new Date(timestampMs(value));
  const base = date.toISOString();
  const milliseconds = date.getUTCMilliseconds();
  return milliseconds === 0
    ? `${base.slice(0, 19)}+00:00`
    : `${base.slice(0, 23)}000+00:00`;
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([, item]) => item !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonical(item)]),
    );
  }
  return value;
}

export function stableJson(value: JsonValue | Readonly<Record<string, unknown>>): string {
  return `${JSON.stringify(canonical(value), null, 2)}\n`;
}

function contextValue(item: ContextSignal): Record<string, unknown> {
  return {
    kind: item.kind,
    evidence_id: item.evidenceId,
    ...(item.title === undefined ? {} : { title: item.title }),
    ...(item.project === undefined ? {} : { project: item.project }),
    ...(item.file === undefined ? {} : { file: item.file }),
    ...(item.urlHost === undefined ? {} : { host: item.urlHost }),
    ...(item.urlPath === undefined ? {} : { path: item.urlPath }),
    ...(item.language === undefined ? {} : { language: item.language }),
  };
}

function sliceValue(item: ActivitySlice): Record<string, unknown> {
  return {
    start: pythonIsoTimestamp(item.start),
    end: pythonIsoTimestamp(item.end),
    focused: item.focused,
    duration_seconds: durationSeconds(item.start, item.end),
    application: item.app ?? null,
    title: item.title ?? null,
    contexts: item.contexts.map(contextValue),
    evidence_ids: [...item.evidenceIds],
  };
}

function sessionValue(item: ActivitySession, details: boolean): Record<string, unknown> {
  return {
    id: item.sessionId,
    start: pythonIsoTimestamp(item.start),
    end: pythonIsoTimestamp(item.end),
    active_seconds: item.activeSeconds,
    focused_seconds: item.focusedSeconds ?? null,
    label: item.label,
    outcome_signals: item.outcomeSignals.map((signal) => ({
      code: signal.code,
      label: signal.label,
      evidence_ids: [...signal.evidenceIds],
    })),
    ...(details ? {
      evidence_ids: [...item.evidenceIds],
      slices: item.slices.map(sliceValue),
    } : {}),
  };
}

export function renderSessionJson(bundle: SessionBundle, options: SessionJsonOptions = {}): string {
  return stableJson({
    schema: "daytrace.session-bundle.v1",
    date: bundle.day,
    timezone: bundle.timezoneName,
    timezone_status: "inferred_at_query",
    focused_seconds: bundle.focusedSeconds ?? null,
    sessions: [...bundle.sessions]
      .sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.sessionId.localeCompare(right.sessionId))
      .map((item) => sessionValue(item, options.details ?? false)),
    diagnostics: bundle.diagnostics.map((item) => ({ code: item.code, count: item.count })),
  });
}

export function episodeValue(item: ActivityEpisode, details: boolean): Record<string, unknown> {
  return {
    id: item.episodeId,
    start: pythonIsoTimestamp(item.start),
    end: pythonIsoTimestamp(item.end),
    active_seconds: item.activeSeconds,
    focused_seconds: item.focusedSeconds ?? null,
    label: item.label,
    anchors: item.anchors.map((value) => ({ kind: value.kind, value: value.value })),
    applications: item.applications.map((value) => ({ value: value.value, count: value.count })),
    activity_labels: item.activityLabels.map((value) => ({ value: value.value, count: value.count })),
    transition_count: item.sessionIds.length,
    outcome_signals: item.outcomeSignals.map((value) => ({ code: value.code, label: value.label })),
    ...(details ? { session_ids: [...item.sessionIds], evidence_ids: [...item.evidenceIds] } : {}),
  };
}

export function renderEpisodeJson(bundle: EpisodeBundle, options: EpisodeJsonOptions = {}): string {
  return stableJson({
    schema: "daytrace.episode-bundle.v1",
    date: bundle.day,
    timezone: bundle.timezoneName,
    timezone_status: "inferred_at_query",
    focused_seconds: bundle.focusedSeconds ?? null,
    episodes: [...bundle.episodes]
      .sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.episodeId.localeCompare(right.episodeId))
      .map((item) => episodeValue(item, options.details ?? false)),
    diagnostics: bundle.diagnostics.map((item) => ({ code: item.code, count: item.count })),
    ...(options.raw ? {
      sessions: [...bundle.sessions]
        .sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.sessionId.localeCompare(right.sessionId))
        .map((item) => sessionValue(item, true)),
    } : {}),
  });
}

export interface DigestJsonOptions {
  readonly details?: boolean;
}

export function renderDigestJson(
  bundle: EpisodeBundle,
  digest: WorkstreamDigest,
  provenance: SummaryProvenance,
  options: DigestJsonOptions = {},
): string {
  const episodeById = new Map(bundle.episodes.map((item) => [item.episodeId, item]));
  return stableJson({
    schema: "daytrace.workstream-report.v2",
    date: bundle.day,
    timezone: bundle.timezoneName,
    timezone_status: "inferred_at_query",
    focused_seconds: bundle.focusedSeconds ?? null,
    summary: {
      provider: provenance.provider,
      model: provenance.model,
      prompt_schema: provenance.promptSchema,
      input_tokens: provenance.inputTokens ?? null,
      output_tokens: provenance.outputTokens ?? null,
      request_count: provenance.requestCount,
    },
    workstreams: digest.workstreams.map((item) => {
      const episodes = item.episodeIds.map((id) => episodeById.get(id)!);
      return {
        label: item.label,
        confidence: item.confidence,
        active_seconds: episodes.reduce((total, episode) => total + episode.activeSeconds, 0),
        episode_ids: [...item.episodeIds],
        topics: item.topics.map((topic) => ({ text: topic.text, evidence: [...topic.evidence] })),
        outcomes: item.outcomes.map((outcome) => ({ text: outcome.text, strength: outcome.strength, evidence: [...outcome.evidence] })),
        activity: episodes.map((episode) => episodeValue(episode, options.details ?? false)),
      };
    }),
    unassigned_activity: digest.unassignedEpisodeIds.map((id) => episodeValue(episodeById.get(id)!, options.details ?? false)),
    diagnostics: bundle.diagnostics.map((item) => ({ code: item.code, count: item.count })),
  });
}

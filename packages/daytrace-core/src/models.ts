export type IsoDate = string;
export type IsoTimestamp = string;

export type SourceKind = "current-window" | "afk" | "editor" | "browser";
export type DiagnosticCode =
  | "non-positive-event"
  | "naive-timestamp"
  | "unsupported-bucket"
  | "window-conflict"
  | "sanitized-field";
export type Confidence = "high" | "medium" | "low";
export type OutcomeStrength = "observed" | "likely" | "none";
export type SummaryPass = "chunk" | "merge";
export type ProviderFailureKind =
  | "authentication"
  | "rate-limit"
  | "network"
  | "service"
  | "request";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | readonly JsonValue[];
export interface JsonObject {
  readonly [key: string]: JsonValue;
}

export interface ServerEndpoint {
  readonly protocol: "http" | "https";
  readonly host: string;
  readonly port: number;
}

export interface ServerInfo {
  readonly version: string;
  readonly testing: boolean;
}

export interface DayWindow {
  readonly timezoneName: string;
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
}

export interface RawBucket {
  readonly id: string;
  readonly type: string;
  readonly client: string;
  readonly hostname: string;
}

export interface RawEvent {
  readonly id: string;
  readonly timestamp: IsoTimestamp;
  readonly durationSeconds: number;
  readonly data: Readonly<Record<string, unknown>>;
}

export interface DiagnosticCount {
  readonly code: DiagnosticCode;
  readonly count: number;
}

export interface ActivityRecord {
  readonly eventId: string;
  readonly bucketId: string;
  readonly kind: SourceKind;
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
  readonly app?: string;
  readonly title?: string;
  readonly project?: string;
  readonly file?: string;
  readonly urlHost?: string;
  readonly urlPath?: string;
  readonly language?: string;
  readonly status?: string;
}

export interface SanitizedObservation {
  readonly evidenceId: string;
  readonly kind: SourceKind;
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
  readonly app?: string;
  readonly title?: string;
  readonly project?: string;
  readonly file?: string;
  readonly urlHost?: string;
  readonly urlPath?: string;
  readonly language?: string;
}

export interface ContextSignal {
  readonly kind: SourceKind;
  readonly evidenceId: string;
  readonly title?: string;
  readonly project?: string;
  readonly file?: string;
  readonly urlHost?: string;
  readonly urlPath?: string;
  readonly language?: string;
}

export interface ActivitySlice {
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
  readonly focused: boolean;
  readonly app?: string;
  readonly title?: string;
  readonly contexts: readonly ContextSignal[];
  readonly evidenceIds: readonly string[];
}

export interface OutcomeSignal {
  readonly code: string;
  readonly label: string;
  readonly evidenceIds: readonly string[];
}

export interface ActivitySession {
  readonly sessionId: string;
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
  readonly activeSeconds: number;
  readonly focusedSeconds?: number;
  readonly label: string;
  readonly slices: readonly ActivitySlice[];
  readonly evidenceIds: readonly string[];
  readonly outcomeSignals: readonly OutcomeSignal[];
}

export interface SessionBundle {
  readonly day: IsoDate;
  readonly timezoneName: string;
  readonly focusedSeconds?: number;
  readonly sessions: readonly ActivitySession[];
  readonly diagnostics: readonly DiagnosticCount[];
}

export interface ActivityAnchor {
  readonly kind: string;
  readonly value: string;
}

export interface ActivityLabelCount {
  readonly value: string;
  readonly count: number;
}

export interface ActivityEpisode {
  readonly episodeId: string;
  readonly start: IsoTimestamp;
  readonly end: IsoTimestamp;
  readonly activeSeconds: number;
  readonly focusedSeconds?: number;
  readonly label: string;
  readonly sessionIds: readonly string[];
  readonly anchors: readonly ActivityAnchor[];
  readonly applications: readonly ActivityLabelCount[];
  readonly activityLabels: readonly ActivityLabelCount[];
  readonly outcomeSignals: readonly OutcomeSignal[];
  readonly evidenceIds: readonly string[];
}

export interface EpisodeBundle {
  readonly day: IsoDate;
  readonly timezoneName: string;
  readonly focusedSeconds?: number;
  readonly episodes: readonly ActivityEpisode[];
  readonly sessions: readonly ActivitySession[];
  readonly diagnostics: readonly DiagnosticCount[];
}

export interface TopicSummary {
  readonly text: string;
  readonly evidence: readonly string[];
}

export interface OutcomeSummary {
  readonly text: string;
  readonly strength: OutcomeStrength;
  readonly evidence: readonly string[];
}

export interface WorkstreamSummary {
  readonly label: string;
  readonly confidence: Confidence;
  readonly episodeIds: readonly string[];
  readonly topics: readonly TopicSummary[];
  readonly outcomes: readonly OutcomeSummary[];
}

export interface WorkstreamDigest {
  readonly workstreams: readonly WorkstreamSummary[];
  readonly unassignedEpisodeIds: readonly string[];
}

export interface SummaryRequest {
  readonly schema: "daytrace.summary-request.v2";
  readonly passKind: "chunk";
  readonly payload: JsonObject;
  readonly characterCount: number;
  readonly episodeIds: readonly string[];
  readonly dataCategories: readonly string[];
}

export interface SummaryPlan {
  readonly requests: readonly SummaryRequest[];
  readonly episodeCount: number;
  readonly inputCharacterCount: number;
  readonly plannedRequestCount: number;
  readonly dataCategories: readonly string[];
}

export interface MergeRequest {
  readonly schema: "daytrace.merge-request.v1";
  readonly passKind: "merge";
  readonly payload: JsonObject;
  readonly characterCount: number;
  readonly provisionalIds: readonly string[];
}

export interface MergeGroup {
  readonly label: string;
  readonly confidence: Confidence;
  readonly provisionalIds: readonly string[];
}

export interface ProviderResponse {
  readonly payload: unknown;
  readonly provider: string;
  readonly model: string;
  readonly inputTokens?: number;
  readonly outputTokens?: number;
  readonly responseId?: string;
  readonly requestId?: string;
}

export interface SummaryFailureContext {
  readonly provider: string;
  readonly model: string;
  readonly stage: SummaryPass;
  readonly callIndex: number;
  readonly requestCharacterCount: number;
  readonly itemIds: readonly string[];
  readonly responseId?: string;
  readonly requestId?: string;
}

export interface SummaryProvenance {
  readonly provider: string;
  readonly model: string;
  readonly promptSchema: string;
  readonly inputTokens?: number;
  readonly outputTokens?: number;
  readonly requestCount: number;
}

export interface ApplicationTotal {
  readonly app: string;
  readonly seconds: number;
}

export interface ActivityReport {
  readonly day: IsoDate;
  readonly timezoneName: string;
  readonly project?: string;
  readonly activeSeconds?: number;
  readonly sources: readonly SourceKind[];
  readonly timeline: readonly ActivityRecord[];
  readonly applications: readonly ApplicationTotal[];
}

export type ProgressStage =
  | "activitywatch:info"
  | "activitywatch:buckets"
  | "activitywatch:events"
  | "pipeline:normalize"
  | "pipeline:sanitize"
  | "pipeline:fuse"
  | "pipeline:sessions"
  | "pipeline:episodes"
  | "summary:chunk"
  | "summary:response"
  | "summary:validate"
  | "summary:repair"
  | "summary:merge"
  | "complete";

export interface ProgressEvent {
  readonly stage: ProgressStage;
  readonly elapsedSeconds: number;
  readonly current?: number;
  readonly total?: number;
}

export type ProgressCallback = (event: ProgressEvent) => void;

export interface ActivityWatchRequest {
  readonly server: string;
  readonly path: string;
  readonly query?: Readonly<Record<string, string>>;
  readonly signal?: AbortSignal;
}

export interface ActivityWatchTransport {
  request(input: ActivityWatchRequest): Promise<unknown>;
}

export interface ProviderRequest {
  readonly passKind: SummaryPass;
  readonly payload: JsonObject;
  readonly instructions: string;
  readonly responseFormat: JsonObject;
}

export interface ProviderCallOptions {
  readonly signal?: AbortSignal;
  readonly onProgress?: ProgressCallback;
}

export interface SummaryProvider {
  complete(
    request: ProviderRequest,
    options?: ProviderCallOptions,
  ): Promise<ProviderResponse>;
}

export interface SummarizedBundle {
  readonly digest: WorkstreamDigest;
  readonly provenance: SummaryProvenance;
}

export type SummaryOutcome =
  | ({ readonly kind: "ai" } & SummarizedBundle)
  | {
      readonly kind: "deterministic";
      readonly bundle: EpisodeBundle;
      readonly failure: DaytraceFailure;
    };

export interface DaytraceFailure {
  readonly code: string;
  readonly field?: string;
  readonly context?: SummaryFailureContext;
  readonly responseShape?: Readonly<Record<string, JsonValue>>;
}

export class DaytraceError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = new.target.name;
    this.code = code;
  }
}

export class DaytraceInputError extends DaytraceError {}
export class ActivityWatchConnectionError extends DaytraceError {}
export class EpisodeInvariantError extends DaytraceError {}
export class CloudPrivacyError extends DaytraceError {}
export class SummaryProviderError extends DaytraceError {
  readonly kind: ProviderFailureKind;

  constructor(kind: ProviderFailureKind = "request") {
    super("provider-request", "summary provider request failed");
    this.kind = kind;
  }
}

export class SummaryValidationError extends DaytraceError {
  readonly field: string;
  readonly context?: SummaryFailureContext;
  readonly responseShape?: Readonly<Record<string, JsonValue>>;

  constructor(
    code: string,
    field: string,
    options?: {
      readonly context?: SummaryFailureContext;
      readonly responseShape?: Readonly<Record<string, JsonValue>>;
    },
  ) {
    super(code, "invalid structured summary response");
    this.field = field;
    if (options?.context !== undefined) this.context = options.context;
    if (options?.responseShape !== undefined) this.responseShape = options.responseShape;
  }
}

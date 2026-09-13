import type {
  ActivitySession,
  ActivitySlice,
  ContextSignal,
  SanitizedObservation,
  SessionBundle,
} from "../src/models.js";

const BASE = Date.parse("2026-09-10T09:00:00.000Z");

export function iso(minutes: number): string {
  return new Date(BASE + minutes * 60_000).toISOString();
}

export function observation(
  startMinutes: number,
  durationMinutes: number,
  options: {
    readonly evidenceId?: string;
    readonly kind?: SanitizedObservation["kind"];
    readonly app?: string | undefined;
    readonly title?: string | undefined;
    readonly project?: string;
    readonly file?: string;
    readonly urlHost?: string;
    readonly urlPath?: string;
    readonly language?: string;
  } = {},
): SanitizedObservation {
  const app = Object.hasOwn(options, "app") ? options.app : "Code";
  const title = Object.hasOwn(options, "title") ? options.title : "Demo";
  return {
    evidenceId: options.evidenceId ?? "evidence-0001",
    kind: options.kind ?? "current-window",
    start: iso(startMinutes),
    end: iso(startMinutes + durationMinutes),
    ...(app === undefined ? {} : { app }),
    ...(title === undefined ? {} : { title }),
    ...(options.project === undefined ? {} : { project: options.project }),
    ...(options.file === undefined ? {} : { file: options.file }),
    ...(options.urlHost === undefined ? {} : { urlHost: options.urlHost }),
    ...(options.urlPath === undefined ? {} : { urlPath: options.urlPath }),
    ...(options.language === undefined ? {} : { language: options.language }),
  };
}

export function slice(
  startMinutes: number,
  durationMinutes: number,
  options: {
    readonly app?: string;
    readonly title?: string;
    readonly focused?: boolean;
    readonly urlHost?: string;
    readonly urlPath?: string;
    readonly project?: string;
    readonly file?: string;
    readonly evidenceIds?: readonly string[];
  } = {},
): ActivitySlice {
  const evidenceIds = options.evidenceIds ?? ["evidence-0001"];
  const context: ContextSignal | undefined = (
    options.urlHost !== undefined
    || options.urlPath !== undefined
    || options.project !== undefined
    || options.file !== undefined
  ) ? {
      kind: "browser",
      evidenceId: evidenceIds[0] ?? "evidence-0001",
      ...(options.urlHost === undefined ? {} : { urlHost: options.urlHost }),
      ...(options.urlPath === undefined ? {} : { urlPath: options.urlPath }),
      ...(options.project === undefined ? {} : { project: options.project }),
      ...(options.file === undefined ? {} : { file: options.file }),
    } : undefined;
  return {
    start: iso(startMinutes),
    end: iso(startMinutes + durationMinutes),
    focused: options.focused ?? true,
    ...(options.app === undefined ? { app: "Code" } : { app: options.app }),
    ...(options.title === undefined ? {} : { title: options.title }),
    contexts: context === undefined ? [] : [context],
    evidenceIds,
  };
}

export function session(
  sessionId: string,
  label: string,
  slices: readonly ActivitySlice[],
): ActivitySession {
  const activeSeconds = slices.reduce(
    (total, item) => total + (Date.parse(item.end) - Date.parse(item.start)) / 1000,
    0,
  );
  const focused = slices.filter((item) => item.focused).reduce(
    (total, item) => total + (Date.parse(item.end) - Date.parse(item.start)) / 1000,
    0,
  );
  return {
    sessionId,
    start: slices[0]?.start ?? iso(0),
    end: slices.at(-1)?.end ?? iso(0),
    activeSeconds,
    ...(focused === 0 ? {} : { focusedSeconds: focused }),
    label,
    slices,
    evidenceIds: [...new Set(slices.flatMap((item) => item.evidenceIds))].sort(),
    outcomeSignals: [],
  };
}

export function sessionBundle(sessions: readonly ActivitySession[]): SessionBundle {
  return {
    day: "2026-09-10",
    timezoneName: "UTC",
    focusedSeconds: sessions.reduce((total, item) => total + (item.focusedSeconds ?? 0), 0),
    sessions,
    diagnostics: [],
  };
}

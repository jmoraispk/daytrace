import { EpisodeInvariantError } from "./models.js";
import type {
  ActivityAnchor,
  ActivityEpisode,
  ActivityLabelCount,
  ActivitySession,
  EpisodeBundle,
  OutcomeSignal,
  SessionBundle,
} from "./models.js";
import { timestampMs } from "./time.js";

const BRIDGE_GAP_SECONDS = 5 * 60;
const ONE_SIDED_GAP_SECONDS = 2 * 60;
const GENERIC_LABELS = new Set([
  "chatgpt", "powershell", "new tab", "inbox", "slack", "outlook",
  "explorer", "unknown", "unknown activity",
]);
const COMMUNICATION_TITLE = /(\(DM\).*Slack|\b(?:Inbox|Calendar).*Outlook|\bMicrosoft Teams$)/i;
const ANCHOR_PRIORITY: Readonly<Record<string, number>> = { repository: 0, project: 1, file: 2, title: 3, domain: 4 };
const OUTCOME_LABEL_CODES = new Set(["named-repository-appeared", "checkout-success", "installer-started"]);

export function isGeneric(value: string): boolean {
  const folded = value.toLocaleLowerCase().replace(/\.exe$/, "");
  return GENERIC_LABELS.has(folded) || COMMUNICATION_TITLE.test(value);
}

function compareAnchors(left: ActivityAnchor, right: ActivityAnchor): number {
  return (ANCHOR_PRIORITY[left.kind] ?? 99) - (ANCHOR_PRIORITY[right.kind] ?? 99)
    || left.value.toLocaleLowerCase().localeCompare(right.value.toLocaleLowerCase())
    || left.value.localeCompare(right.value);
}

export function sessionAnchors(session: ActivitySession): readonly ActivityAnchor[] {
  const found = new Map<string, ActivityAnchor>();
  const add = (kind: string, raw: string | undefined): void => {
    if (raw === undefined || raw.length === 0) return;
    const value = raw.trim().split(/\s+/u).join(" ");
    const key = `${kind}\0${value.toLocaleLowerCase()}`;
    if (!found.has(key)) found.set(key, { kind, value });
  };
  for (const item of session.slices) {
    for (const context of item.contexts) {
      add("repository", context.urlPath);
      add("project", context.project);
      add("file", context.file);
      if (context.title !== undefined && !isGeneric(context.title)) add("title", context.title);
      if (context.urlHost !== undefined && context.urlPath === undefined) add("domain", context.urlHost);
    }
    if (item.title !== undefined && !isGeneric(item.title)) add("title", item.title);
  }
  if (found.size === 0 && !isGeneric(session.label)) add("title", session.label);
  return [...found.values()].sort(compareAnchors);
}

export function anchorsCompatible(left: readonly ActivityAnchor[], right: readonly ActivityAnchor[]): boolean {
  const keys = new Set(left.map((item) => `${item.kind}\0${item.value.toLocaleLowerCase()}`));
  return right.some((item) => keys.has(`${item.kind}\0${item.value.toLocaleLowerCase()}`));
}

function counts(values: readonly string[]): readonly ActivityLabelCount[] {
  const totals = new Map<string, number>();
  for (const value of values) totals.set(value, (totals.get(value) ?? 0) + 1);
  return [...totals.entries()]
    .sort(([leftValue, leftCount], [rightValue, rightCount]) => rightCount - leftCount
      || leftValue.toLocaleLowerCase().localeCompare(rightValue.toLocaleLowerCase())
      || leftValue.localeCompare(rightValue))
    .map(([value, count]) => ({ value, count }));
}

function signals(sessions: readonly ActivitySession[]): readonly OutcomeSignal[] {
  const grouped = new Map<string, { code: string; label: string; evidenceIds: string[] }>();
  for (const session of sessions) {
    for (const signal of session.outcomeSignals) {
      const key = `${signal.code}\0${signal.label}`;
      const current = grouped.get(key) ?? { code: signal.code, label: signal.label, evidenceIds: [] };
      for (const evidenceId of signal.evidenceIds) {
        if (!current.evidenceIds.includes(evidenceId)) current.evidenceIds.push(evidenceId);
      }
      grouped.set(key, current);
    }
  }
  return [...grouped.values()];
}

function episode(index: number, sessions: readonly ActivitySession[]): ActivityEpisode {
  const unique = new Map<string, ActivityAnchor>();
  for (const session of sessions) {
    for (const anchor of sessionAnchors(session)) {
      const key = `${anchor.kind}\0${anchor.value}`;
      if (!unique.has(key)) unique.set(key, anchor);
    }
  }
  const anchors = [...unique.values()].sort(compareAnchors);
  const outcomeSignals = signals(sessions);
  const namedOutcome = outcomeSignals.find((item) => OUTCOME_LABEL_CODES.has(item.code))?.label;
  const label = anchors[0]?.value.replace(/^\//, "") ?? namedOutcome ?? sessions[0]?.label ?? "Unknown activity";
  const focused = sessions.flatMap((item) => item.focusedSeconds === undefined ? [] : [item.focusedSeconds]);
  return {
    episodeId: `episode-${String(index).padStart(3, "0")}`,
    start: sessions.reduce((value, item) => timestampMs(item.start) < timestampMs(value) ? item.start : value, sessions[0]!.start),
    end: sessions.reduce((value, item) => timestampMs(item.end) > timestampMs(value) ? item.end : value, sessions[0]!.end),
    activeSeconds: sessions.reduce((total, item) => total + item.activeSeconds, 0),
    ...(focused.length === 0 ? {} : { focusedSeconds: focused.reduce((total, value) => total + value, 0) }),
    label,
    sessionIds: sessions.map((item) => item.sessionId),
    anchors,
    applications: counts(sessions.flatMap((item) => item.slices.flatMap((slice) => slice.app === undefined ? [] : [slice.app]))),
    activityLabels: counts(sessions.map((item) => item.label)),
    outcomeSignals,
    evidenceIds: [...new Set(sessions.flatMap((item) => item.evidenceIds))],
  };
}

function gapSeconds(start: string, end: string): number {
  return (timestampMs(start) - timestampMs(end)) / 1000;
}

function isClose(left: number, right: number): boolean {
  return Math.abs(left - right) <= Math.max(1e-9, 1e-12 * Math.max(Math.abs(left), Math.abs(right)));
}

export function compactSessions(bundle: SessionBundle): EpisodeBundle {
  const sessions = [...bundle.sessions].sort(
    (left, right) => timestampMs(left.start) - timestampMs(right.start) || timestampMs(left.end) - timestampMs(right.end),
  );
  const anchors = sessions.map(sessionAnchors);
  const strong = anchors.flatMap((value, index) => value.length > 0 ? [index] : []);
  const groups: Set<number>[] = [];
  for (const sessionIndex of strong) {
    const previousGroup = groups.at(-1);
    if (previousGroup !== undefined) {
      const previousIndex = Math.max(...previousGroup);
      if (
        anchorsCompatible(anchors[previousIndex] ?? [], anchors[sessionIndex] ?? [])
        && gapSeconds(sessions[sessionIndex]!.start, sessions[previousIndex]!.end) <= BRIDGE_GAP_SECONDS
      ) {
        for (let index = previousIndex + 1; index <= sessionIndex; index += 1) previousGroup.add(index);
        continue;
      }
    }
    groups.push(new Set([sessionIndex]));
  }

  const assigned = new Set(groups.flatMap((group) => [...group]));
  sessions.forEach((session, sessionIndex) => {
    if (assigned.has(sessionIndex)) return;
    const candidates = new Set<number>();
    groups.forEach((group, groupIndex) => {
      const first = sessions[Math.min(...group)];
      const last = sessions[Math.max(...group)];
      if (first === undefined || last === undefined) return;
      if (timestampMs(last.end) <= timestampMs(session.start) && gapSeconds(session.start, last.end) <= ONE_SIDED_GAP_SECONDS) candidates.add(groupIndex);
      if (timestampMs(session.end) <= timestampMs(first.start) && gapSeconds(first.start, session.end) <= ONE_SIDED_GAP_SECONDS) candidates.add(groupIndex);
    });
    if (candidates.size === 1) {
      const groupIndex = [...candidates][0];
      if (groupIndex !== undefined) groups[groupIndex]?.add(sessionIndex);
      assigned.add(sessionIndex);
    }
  });

  const weakGroups: Set<number>[] = [];
  sessions.forEach((session, sessionIndex) => {
    if (assigned.has(sessionIndex)) return;
    const previousGroup = weakGroups.at(-1);
    const previousIndex = previousGroup === undefined ? undefined : Math.max(...previousGroup);
    if (
      previousGroup !== undefined
      && previousIndex !== undefined
      && sessionIndex === previousIndex + 1
      && gapSeconds(session.start, sessions[previousIndex]!.end) <= BRIDGE_GAP_SECONDS
    ) previousGroup.add(sessionIndex);
    else weakGroups.push(new Set([sessionIndex]));
  });
  groups.push(...weakGroups);
  groups.sort((left, right) => timestampMs(sessions[Math.min(...left)]!.start) - timestampMs(sessions[Math.min(...right)]!.start) || Math.min(...left) - Math.min(...right));

  const episodes = groups.map((group, index) => episode(index + 1, [...group].sort((a, b) => a - b).map((item) => sessions[item]!)));
  const actualMembers = episodes.flatMap((item) => item.sessionIds);
  const expectedMembers = sessions.map((item) => item.sessionId);
  if (new Set(actualMembers).size !== actualMembers.length || [...actualMembers].sort().join("\0") !== [...expectedMembers].sort().join("\0")) {
    throw new EpisodeInvariantError("episode-membership", "episode membership was not conserved");
  }
  const episodeSeconds = episodes.reduce((total, item) => total + item.activeSeconds, 0);
  const sessionSeconds = sessions.reduce((total, item) => total + item.activeSeconds, 0);
  if (!isClose(episodeSeconds, sessionSeconds)) {
    throw new EpisodeInvariantError("episode-duration", "episode duration was not conserved");
  }
  return {
    day: bundle.day,
    timezoneName: bundle.timezoneName,
    ...(bundle.focusedSeconds === undefined ? {} : { focusedSeconds: bundle.focusedSeconds }),
    episodes,
    sessions,
    diagnostics: bundle.diagnostics,
  };
}

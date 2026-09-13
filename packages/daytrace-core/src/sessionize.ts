import type {
  ActivitySession,
  ActivitySlice,
  DayWindow,
  DiagnosticCount,
  IsoDate,
  OutcomeSignal,
  SessionBundle,
} from "./models.js";
import { durationSeconds, timestampMs } from "./time.js";

const BRIDGE_LIMIT_SECONDS = 20;
const SESSION_GAP_SECONDS = 5 * 60;
const GENERIC = new Set([
  "chatgpt", "powershell", "new tab", "inbox", "slack", "outlook",
  "new repository", "success page", "installation options",
]);
const STANDALONE_GENERIC = new Set(["chatgpt", "powershell", "new tab", "inbox", "slack", "outlook"]);

function specificKey(item: ActivitySlice): string | undefined {
  for (const signal of item.contexts) {
    if (signal.project !== undefined) return signal.project.toLocaleLowerCase();
    if (signal.urlPath !== undefined) return signal.urlPath.toLocaleLowerCase();
    if (signal.file !== undefined) return signal.file.toLocaleLowerCase();
  }
  if (item.title !== undefined && !GENERIC.has(item.title.toLocaleLowerCase())) {
    return item.title.toLocaleLowerCase();
  }
  return undefined;
}

function pathName(value: string): string {
  return value.split(/[\\/]/).filter(Boolean).at(-1) ?? value;
}

function label(item: ActivitySlice): string {
  for (const signal of item.contexts) {
    if (signal.project !== undefined) return pathName(signal.project);
    if (signal.urlPath !== undefined) return signal.urlPath.replace(/^\/+|\/+$/g, "");
    if (signal.title !== undefined) return signal.title;
  }
  return item.title ?? item.app ?? "Unknown activity";
}

function genericName(item: ActivitySlice): string {
  return (item.title ?? item.app ?? "").toLocaleLowerCase().replace(/\.exe$/, "");
}

function evidenceFor(slices: readonly ActivitySlice[]): readonly string[] {
  return [...new Set(slices.flatMap((item) => item.evidenceIds))].sort();
}

function outcomeSignals(slices: readonly ActivitySlice[]): readonly OutcomeSignal[] {
  const signals: OutcomeSignal[] = [];
  const titles = slices.map((item) => (item.title ?? "").toLocaleLowerCase());
  for (let index = 0; index < titles.length - 1; index += 1) {
    const matchingLater = slices.slice(index + 1).find(
      (later) => later.contexts.some((signal) => signal.urlPath !== undefined),
    );
    if (titles[index] === "new repository" && matchingLater !== undefined) {
      const path = matchingLater.contexts.find((signal) => signal.urlPath !== undefined)?.urlPath;
      if (path !== undefined) {
        signals.push({
          code: "named-repository-appeared",
          label: `Named repository appeared: ${path.replace(/^\/+|\/+$/g, "")}`,
          evidenceIds: evidenceFor([slices[index] as ActivitySlice, matchingLater]),
        });
      }
      break;
    }
  }
  if (titles.some((title) => title === "success page" || title === "checkout success")) {
    signals.push({ code: "checkout-success", label: "A checkout success state appeared", evidenceIds: evidenceFor(slices) });
  }
  if (slices.some((item) => (item.app ?? "").toLocaleLowerCase().includes("installer"))) {
    signals.push({ code: "installer-started", label: "An installer was started", evidenceIds: evidenceFor(slices) });
  }
  return signals;
}

function bridgeLinks(items: readonly ActivitySlice[]): Set<number> {
  const links = new Set<number>();
  for (let index = 1; index < items.length - 1; index += 1) {
    const previous = items[index - 1];
    const current = items[index];
    const next = items[index + 1];
    if (previous === undefined || current === undefined || next === undefined) continue;
    const previousKey = specificKey(previous);
    const nextKey = specificKey(next);
    if (
      durationSeconds(current.start, current.end) < BRIDGE_LIMIT_SECONDS
      && previousKey !== undefined
      && previousKey === nextKey
    ) {
      links.add(index);
      links.add(index + 1);
    }
  }
  return links;
}

function startsNewSession(
  previous: ActivitySlice,
  current: ActivitySlice,
  boundaryIndex: number,
  links: ReadonlySet<number>,
): boolean {
  if (links.has(boundaryIndex)) return false;
  if ((timestampMs(current.start) - timestampMs(previous.end)) / 1000 > SESSION_GAP_SECONDS) return true;
  const previousKey = specificKey(previous);
  const currentKey = specificKey(current);
  if (previousKey !== undefined && currentKey !== undefined) return previousKey !== currentKey;
  if (STANDALONE_GENERIC.has(genericName(previous))) return true;
  if (STANDALONE_GENERIC.has(genericName(current))) return true;
  if (previousKey === undefined && currentKey === undefined) return genericName(previous) !== genericName(current);
  return false;
}

function makeSession(index: number, slices: readonly ActivitySlice[]): ActivitySession {
  const activeSeconds = slices.reduce((total, item) => total + durationSeconds(item.start, item.end), 0);
  const focused = slices.filter((item) => item.focused).map((item) => durationSeconds(item.start, item.end));
  const labelSource = slices.find((item) => specificKey(item) !== undefined) ?? slices[0];
  if (labelSource === undefined) throw new Error("empty session");
  return {
    sessionId: `session-${String(index).padStart(3, "0")}`,
    start: slices.reduce((value, item) => timestampMs(item.start) < timestampMs(value) ? item.start : value, slices[0]!.start),
    end: slices.reduce((value, item) => timestampMs(item.end) > timestampMs(value) ? item.end : value, slices[0]!.end),
    activeSeconds,
    ...(focused.length === 0 ? {} : { focusedSeconds: focused.reduce((total, value) => total + value, 0) }),
    label: label(labelSource),
    slices,
    evidenceIds: evidenceFor(slices),
    outcomeSignals: outcomeSignals(slices),
  };
}

export function sessionize(
  day: IsoDate,
  window: DayWindow,
  slices: readonly ActivitySlice[],
  diagnostics: readonly DiagnosticCount[],
): SessionBundle {
  const ordered = [...slices].sort(
    (left, right) => timestampMs(left.start) - timestampMs(right.start) || timestampMs(left.end) - timestampMs(right.end),
  );
  const groups: ActivitySlice[][] = [];
  const links = bridgeLinks(ordered);
  ordered.forEach((item, index) => {
    const previous = ordered[index - 1];
    if (groups.length === 0 || previous === undefined || startsNewSession(previous, item, index, links)) {
      groups.push([item]);
    } else {
      groups.at(-1)?.push(item);
    }
  });
  const sessions = groups.map((group, index) => makeSession(index + 1, group));
  const focused = ordered.filter((item) => item.focused).map((item) => durationSeconds(item.start, item.end));
  return {
    day,
    timezoneName: window.timezoneName,
    ...(focused.length === 0 ? {} : { focusedSeconds: focused.reduce((total, value) => total + value, 0) }),
    sessions,
    diagnostics,
  };
}

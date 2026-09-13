import type {
  ActivitySlice,
  ContextSignal,
  DiagnosticCode,
  SanitizedObservation,
} from "./models.js";
import { timestampMs } from "./time.js";

const BROWSER_APPS = ["edge", "chrome", "firefox", "brave", "opera", "safari"] as const;
const EDITOR_APPS = ["code", "codium", "pycharm", "idea", "sublime", "zed"] as const;

function appMatches(app: string | undefined, families: readonly string[]): boolean {
  const folded = (app ?? "").toLocaleLowerCase();
  return families.some((name) => folded.includes(name));
}

function context(item: SanitizedObservation): ContextSignal {
  return {
    kind: item.kind,
    evidenceId: item.evidenceId,
    ...(item.title === undefined ? {} : { title: item.title }),
    ...(item.project === undefined ? {} : { project: item.project }),
    ...(item.file === undefined ? {} : { file: item.file }),
    ...(item.urlHost === undefined ? {} : { urlHost: item.urlHost }),
    ...(item.urlPath === undefined ? {} : { urlPath: item.urlPath }),
    ...(item.language === undefined ? {} : { language: item.language }),
  };
}

function contextKey(item: ContextSignal): string {
  return JSON.stringify(item);
}

function sameContexts(left: readonly ContextSignal[], right: readonly ContextSignal[]): boolean {
  return left.length === right.length && left.every((item, index) => contextKey(item) === contextKey(right[index] as ContextSignal));
}

function mergeIdenticalTouching(slices: readonly ActivitySlice[]): readonly ActivitySlice[] {
  const merged: ActivitySlice[] = [];
  for (const item of slices) {
    const previous = merged.at(-1);
    if (
      previous !== undefined
      && previous.end === item.start
      && previous.focused === item.focused
      && previous.app === item.app
      && previous.title === item.title
      && sameContexts(previous.contexts, item.contexts)
    ) {
      merged[merged.length - 1] = {
        ...previous,
        end: item.end,
        evidenceIds: [...new Set([...previous.evidenceIds, ...item.evidenceIds])].sort(),
      };
    } else {
      merged.push(item);
    }
  }
  return merged;
}

export function fuseObservations(
  observations: readonly SanitizedObservation[],
  diagnose: (code: DiagnosticCode) => void,
): readonly ActivitySlice[] {
  const items = [...observations].sort(
    (left, right) => timestampMs(left.start) - timestampMs(right.start)
      || left.evidenceId.localeCompare(right.evidenceId),
  );
  const windows = items.filter((item) => item.kind === "current-window");
  const contextItems = items.filter((item) => item.kind !== "current-window");
  const boundaries = [...new Set(items.flatMap((item) => [timestampMs(item.start), timestampMs(item.end)]))]
    .sort((left, right) => left - right);
  const output: ActivitySlice[] = [];
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index];
    const end = boundaries[index + 1];
    if (start === undefined || end === undefined) continue;
    const coveringWindows = windows.filter(
      (item) => timestampMs(item.start) < end && timestampMs(item.end) > start,
    );
    if (coveringWindows.length > 0) {
      if (coveringWindows.length > 1) diagnose("window-conflict");
      const winner = [...coveringWindows].sort((left, right) => left.evidenceId.localeCompare(right.evidenceId))[0];
      if (winner === undefined) continue;
      const contexts = contextItems.filter((item) => {
        if (timestampMs(item.start) >= end || timestampMs(item.end) <= start) return false;
        return (item.kind === "browser" && appMatches(winner.app, BROWSER_APPS))
          || (item.kind === "editor" && appMatches(winner.app, EDITOR_APPS));
      }).map(context).sort((left, right) => left.evidenceId.localeCompare(right.evidenceId));
      output.push({
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        focused: true,
        ...(winner.app === undefined ? {} : { app: winner.app }),
        ...(winner.title === undefined ? {} : { title: winner.title }),
        contexts,
        evidenceIds: [...new Set([winner.evidenceId, ...contexts.map((item) => item.evidenceId)])].sort(),
      });
      continue;
    }
    const covering = contextItems.filter(
      (item) => timestampMs(item.start) < end && timestampMs(item.end) > start,
    );
    if (covering.length > 0) {
      const contexts = covering.map(context).sort((left, right) => left.evidenceId.localeCompare(right.evidenceId));
      output.push({
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
        focused: false,
        contexts,
        evidenceIds: contexts.map((item) => item.evidenceId),
      });
    }
  }
  return mergeIdenticalTouching(output);
}

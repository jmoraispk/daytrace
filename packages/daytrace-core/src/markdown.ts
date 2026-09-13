import { diagnosticMessages } from "./diagnostics.js";
import type {
  ActivityEpisode,
  ActivityRecord,
  ActivityReport,
  ActivitySession,
  ActivitySlice,
  ContextSignal,
  EpisodeBundle,
  SessionBundle,
  SummaryProvenance,
  SourceKind,
  WorkstreamDigest,
  WorkstreamSummary,
} from "./models.js";
import { durationSeconds, timestampMs } from "./time.js";

const SOURCE_LABEL: Readonly<Record<SourceKind, string>> = {
  "current-window": "Current window",
  editor: "Editor",
  browser: "Browser",
  afk: "AFK",
};

export function formatDuration(seconds: number): string {
  if (seconds > 0 && seconds < 60) return "<1m";
  const totalMinutes = Math.max(0, Math.floor((seconds + 30) / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h`;
  return `${minutes}m`;
}

function singleLine(value: string): string {
  return value.replace(/[\r\n]/g, " ").trim().split(/\s+/u).filter(Boolean).join(" ");
}

function htmlEscape(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function escapeMarkdown(value: string): string {
  return htmlEscape(singleLine(value)).replace(/\\/g, "\\\\").replace(/([`*_{}\[\]#+|])/g, "\\$1");
}

export function inlineCode(value: string): string {
  const clean = singleLine(value);
  const runs = clean.match(/`+/g) ?? [];
  const longest = runs.reduce((length, run) => Math.max(length, run.length), 0);
  const fence = "`".repeat(longest + 1);
  const padding = clean.startsWith("`") || clean.endsWith("`") ? " " : "";
  return `${fence}${padding}${clean}${padding}${fence}`;
}

function basename(value?: string): string | undefined {
  return value?.split("/").at(-1)?.split("\\").at(-1);
}

function recordLabel(record: ActivityRecord): string {
  const values = record.kind === "current-window"
    ? [record.app, record.title]
    : record.kind === "browser"
      ? [record.urlHost, record.title]
      : [basename(record.project), basename(record.file), record.language];
  return values.filter((value): value is string => value !== undefined).map(escapeMarkdown).join(" — ")
    || SOURCE_LABEL[record.kind];
}

function localTime(value: string, timezoneName: string): string {
  return new Intl.DateTimeFormat("en-GB-u-hc-h23", {
    timeZone: timezoneName,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(timestampMs(value)));
}

function timeRange(item: { readonly start: string; readonly end: string }, timezoneName: string): string {
  return `${localTime(item.start, timezoneName)}–${localTime(item.end, timezoneName)}`;
}

export function renderMarkdown(report: ActivityReport): string {
  const lines = [`# Activity summary — ${report.day}`, ""];
  if (report.project !== undefined) lines.push(`Project filter: ${inlineCode(report.project)}`);
  lines.push(`Timezone: ${inlineCode(report.timezoneName)}`, "", "## Overview", "");
  if (report.timeline.length === 0) return `${[...lines, "No matching activity.", ""].join("\n")}`;
  lines.push(
    `- Active matched time: ${report.activeSeconds === undefined ? "Unavailable" : formatDuration(report.activeSeconds)}`,
    `- Timeline entries: ${report.timeline.length}`,
    `- Sources: ${report.sources.map((item) => SOURCE_LABEL[item]).join(", ")}`,
    "",
    "## Timeline",
    "",
  );
  for (const record of report.timeline) {
    lines.push(`- ${timeRange(record, report.timezoneName)} (${formatDuration(durationSeconds(record.start, record.end))}) — ${recordLabel(record)}`);
  }
  if (report.applications.length > 0) {
    lines.push("", "## Applications", "");
    for (const item of report.applications) lines.push(`- ${escapeMarkdown(item.app)} — ${formatDuration(item.seconds)}`);
  }
  return `${lines.join("\n")}\n`;
}

function contextLabel(context: ContextSignal): string {
  const values = [context.project, context.file, context.urlHost, context.urlPath, context.title, context.language];
  return values.filter((value): value is string => value !== undefined).map(escapeMarkdown).join(" — ") || context.kind;
}

function appendSessionDetails(lines: string[], item: ActivitySession): void {
  if (item.evidenceIds.length > 0) lines.push(`  - Evidence: ${item.evidenceIds.map(inlineCode).join(", ")}`);
  const contexts = new Map<string, readonly [SourceKind, string]>();
  for (const context of item.slices.flatMap((slice) => slice.contexts)) {
    const value = contextLabel(context);
    contexts.set(`${context.kind}\0${value}`, [context.kind, value]);
  }
  for (const [, [kind, value]] of [...contexts].sort(([left], [right]) => left.localeCompare(right))) {
    lines.push(`  - ${SOURCE_LABEL[kind]}: ${value}`);
  }
  lines.push(`  - Foreground duration: ${item.focusedSeconds === undefined ? "unavailable" : formatDuration(item.focusedSeconds)}`);
}

function appendRawSlices(lines: string[], item: ActivitySession, timezoneName: string): void {
  for (const slice of item.slices) {
    const label = slice.title ?? slice.app ?? "Context evidence";
    const focus = slice.focused ? "focused" : "evidence only";
    lines.push(`  - ${timeRange(slice, timezoneName)} — ${inlineCode(label)} (${formatDuration(durationSeconds(slice.start, slice.end))}, ${focus})`);
  }
}

export interface MarkdownDetailsOptions {
  readonly details?: boolean;
  readonly raw?: boolean;
}

export function renderSessionMarkdown(bundle: SessionBundle, options: MarkdownDetailsOptions = {}): string {
  const focused = bundle.focusedSeconds === undefined ? "Unavailable" : formatDuration(bundle.focusedSeconds);
  const lines = [
    `# DayTrace — ${bundle.day}`,
    "",
    `Timezone: ${inlineCode(bundle.timezoneName)} (inferred at query time)`,
    `Focused activity: ${focused}`,
    "Summary: Deterministic activity sessions",
    "",
    "## Activity sessions",
    "",
  ];
  const sessions = [...bundle.sessions].sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.sessionId.localeCompare(right.sessionId));
  if (sessions.length === 0) lines.push("No activity sessions.");
  for (const item of sessions) {
    lines.push(`- ${timeRange(item, bundle.timezoneName)} — ${inlineCode(item.label)} (${formatDuration(item.activeSeconds)})`);
    for (const signal of item.outcomeSignals) lines.push(`  - Observed signal: ${escapeMarkdown(signal.label)}`);
    if (options.details) appendSessionDetails(lines, item);
    if (options.raw) appendRawSlices(lines, item, bundle.timezoneName);
  }
  if (bundle.diagnostics.length > 0) {
    lines.push("", "## Diagnostics", "");
    for (const message of diagnosticMessages(bundle.diagnostics)) lines.push(`- ${message[0]?.toLocaleUpperCase()}${message.slice(1)}.`);
  }
  return `${lines.join("\n")}\n`;
}

function episodeLine(item: ActivityEpisode, timezoneName: string): string {
  return `- ${timeRange(item, timezoneName)} — ${inlineCode(item.label)} (${formatDuration(item.activeSeconds)})`;
}

export function renderEpisodeMarkdown(bundle: EpisodeBundle, options: MarkdownDetailsOptions = {}): string {
  const focused = bundle.focusedSeconds === undefined ? "Unavailable" : formatDuration(bundle.focusedSeconds);
  const lines = [
    `# DayTrace — ${bundle.day}`,
    "",
    `Timezone: ${inlineCode(bundle.timezoneName)} (inferred at query time)`,
    `Focused activity: ${focused}`,
    "Summary: Deterministic activity episodes",
    "",
    "## Activity episodes",
    "",
  ];
  const episodes = [...bundle.episodes].sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.episodeId.localeCompare(right.episodeId));
  if (episodes.length === 0) lines.push("No activity episodes.");
  for (const item of episodes) {
    lines.push(episodeLine(item, bundle.timezoneName));
    if (item.anchors.length > 0) lines.push(`  - Anchors: ${item.anchors.map((anchor) => `${anchor.kind}: ${escapeMarkdown(anchor.value)}`).join("; ")}`);
    if (item.applications.length > 0) lines.push(`  - Tools: ${item.applications.map((value) => `${escapeMarkdown(value.value)} ×${value.count}`).join(", ")}`);
    lines.push(`  - Activity transitions: ${item.sessionIds.length}`);
    for (const signal of item.outcomeSignals) lines.push(`  - Observed signal: ${escapeMarkdown(signal.label)}`);
    if (options.details) {
      lines.push(`  - Episode ID: ${inlineCode(item.episodeId)}`);
      lines.push(`  - Source sessions: ${item.sessionIds.map(inlineCode).join(", ")}`);
      if (item.activityLabels.length > 0) lines.push(`  - Activity labels: ${item.activityLabels.map((value) => `${escapeMarkdown(value.value)} ×${value.count}`).join(", ")}`);
      if (item.evidenceIds.length > 0) lines.push(`  - Evidence: ${item.evidenceIds.map(inlineCode).join(", ")}`);
      lines.push(`  - Foreground duration: ${item.focusedSeconds === undefined ? "unavailable" : formatDuration(item.focusedSeconds)}`);
    }
  }
  if (options.raw) {
    lines.push("", "## Fine-grained activity", "");
    for (const item of [...bundle.sessions].sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.sessionId.localeCompare(right.sessionId))) {
      lines.push(`- ${timeRange(item, bundle.timezoneName)} — ${inlineCode(item.label)} (${formatDuration(item.activeSeconds)}) — ${inlineCode(item.sessionId)}`);
      appendSessionDetails(lines, item);
      appendRawSlices(lines, item, bundle.timezoneName);
    }
  }
  if (bundle.diagnostics.length > 0) {
    lines.push("", "## Diagnostics", "");
    for (const message of diagnosticMessages(bundle.diagnostics)) lines.push(`- ${message[0]?.toLocaleUpperCase()}${message.slice(1)}.`);
  }
  return `${lines.join("\n")}\n`;
}

function outcomeCell(item: WorkstreamSummary): string {
  const visible = item.outcomes.filter((outcome) => outcome.strength !== "none");
  if (visible.length === 0) return "No completion should be claimed from this trace alone.";
  return visible.map((outcome) => `${outcome.strength === "likely" ? "Likely: " : ""}${escapeMarkdown(outcome.text)}`).join("<br>");
}

function topicCell(item: WorkstreamSummary): string {
  return item.topics.length === 0
    ? "No specific topics identified."
    : item.topics.map((topic) => escapeMarkdown(topic.text)).join("<br>");
}

export interface DigestMarkdownOptions {
  readonly details?: boolean;
}

export function renderDigestMarkdown(
  bundle: EpisodeBundle,
  digest: WorkstreamDigest,
  provenance: SummaryProvenance,
  options: DigestMarkdownOptions = {},
): string {
  const focused = bundle.focusedSeconds === undefined ? "Unavailable" : formatDuration(bundle.focusedSeconds);
  const episodeById = new Map(bundle.episodes.map((item) => [item.episodeId, item]));
  const lines = [
    `# DayTrace — ${bundle.day}`,
    "",
    `Timezone: ${inlineCode(bundle.timezoneName)} (inferred at query time)`,
    `Focused activity: ${focused}`,
    `Summary: AI-assisted workstreams (${inlineCode(provenance.provider)} / ${inlineCode(provenance.model)})`,
  ];
  if (options.details) lines.push(`Provider requests: ${provenance.requestCount}`);
  lines.push(
    "",
    "## What this day appears to contain",
    "",
    "This is a confidence-aware summary inferred from the activity trace. Achievements require evidence of a resulting state, not merely an open application.",
    "",
    "| Project / workstream | Apparent achievements | Work and topics |",
    "| --- | --- | --- |",
  );
  for (const workstream of digest.workstreams) {
    lines.push(`| **${escapeMarkdown(workstream.label)}** | ${outcomeCell(workstream)} | ${topicCell(workstream)} |`);
  }
  if (digest.workstreams.length === 0) lines.push("| _No coherent workstreams identified._ | — | — |");
  if (!options.details) return `${lines.join("\n")}\n`;
  lines.push("", "## Supporting activity", "");
  const confidence = { high: "High", medium: "Medium", low: "Low" } as const;
  for (const workstream of digest.workstreams) {
    const episodes = workstream.episodeIds.map((id) => episodeById.get(id)!);
    lines.push(
      `### ${escapeMarkdown(workstream.label)}`,
      "",
      `Primary allocation · ${confidence[workstream.confidence]} confidence · ${formatDuration(episodes.reduce((total, item) => total + item.activeSeconds, 0))}`,
      "",
    );
    for (const episode of [...episodes].sort((left, right) => timestampMs(left.start) - timestampMs(right.start) || left.episodeId.localeCompare(right.episodeId))) {
      lines.push(episodeLine(episode, bundle.timezoneName));
      lines.push(`  - Episode ID: ${inlineCode(episode.episodeId)}`);
      lines.push(`  - Activity transitions: ${episode.sessionIds.length}`);
    }
  }
  lines.push("", "## Unassigned activity", "");
  if (digest.unassignedEpisodeIds.length === 0) lines.push("None.");
  else for (const id of digest.unassignedEpisodeIds) {
    const episode = episodeById.get(id)!;
    lines.push(episodeLine(episode, bundle.timezoneName));
    lines.push(`  - Episode ID: ${inlineCode(episode.episodeId)}`);
  }
  return `${lines.join("\n")}\n`;
}

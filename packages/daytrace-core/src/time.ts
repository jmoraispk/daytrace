import { DaytraceInputError } from "./models.js";
import type { DayWindow, IsoDate, IsoTimestamp } from "./models.js";

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

interface CalendarParts {
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly hour: number;
  readonly minute: number;
  readonly second: number;
}

function parseDay(day: IsoDate): readonly [number, number, number] {
  const match = DAY.exec(day);
  if (match === null) throw new DaytraceInputError("invalid-day", "invalid day");
  const year = Number(match[1]);
  const month = Number(match[2]);
  const date = Number(match[3]);
  const probe = new Date(Date.UTC(year, month - 1, date));
  if (
    probe.getUTCFullYear() !== year
    || probe.getUTCMonth() !== month - 1
    || probe.getUTCDate() !== date
  ) {
    throw new DaytraceInputError("invalid-day", "invalid day");
  }
  return [year, month, date];
}

function calendarParts(timestampMs: number, timezoneName: string): CalendarParts {
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat("en-CA-u-hc-h23", {
      timeZone: timezoneName,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
  } catch {
    throw new DaytraceInputError("invalid-timezone", "invalid timezone");
  }
  const values = new Map(
    formatter
      .formatToParts(new Date(timestampMs))
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)]),
  );
  return {
    year: values.get("year") ?? 0,
    month: values.get("month") ?? 0,
    day: values.get("day") ?? 0,
    hour: values.get("hour") ?? 0,
    minute: values.get("minute") ?? 0,
    second: values.get("second") ?? 0,
  };
}

function localMidnightMs(year: number, month: number, day: number, timezoneName: string): number {
  const target = Date.UTC(year, month - 1, day);
  let candidate = target;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const local = calendarParts(candidate, timezoneName);
    const interpreted = Date.UTC(
      local.year,
      local.month - 1,
      local.day,
      local.hour,
      local.minute,
      local.second,
    );
    const adjustment = target - interpreted;
    if (adjustment === 0) return candidate;
    candidate += adjustment;
  }
  throw new DaytraceInputError("invalid-timezone", "invalid timezone");
}

export function resolveDay(day: IsoDate, timezoneName: string): DayWindow {
  const [year, month, date] = parseDay(day);
  const next = new Date(Date.UTC(year, month - 1, date + 1));
  const startMs = localMidnightMs(year, month, date, timezoneName);
  const endMs = localMidnightMs(
    next.getUTCFullYear(),
    next.getUTCMonth() + 1,
    next.getUTCDate(),
    timezoneName,
  );
  return {
    timezoneName,
    start: new Date(startMs).toISOString(),
    end: new Date(endMs).toISOString(),
  };
}

export function timestampMs(value: IsoTimestamp): number {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    throw new DaytraceInputError("invalid-timestamp", "invalid timestamp");
  }
  return parsed;
}

export function durationSeconds(start: IsoTimestamp, end: IsoTimestamp): number {
  return (timestampMs(end) - timestampMs(start)) / 1000;
}

export function addSeconds(value: IsoTimestamp, seconds: number): IsoTimestamp {
  return new Date(timestampMs(value) + seconds * 1000).toISOString();
}

export function maxTimestamp(left: IsoTimestamp, right: IsoTimestamp): IsoTimestamp {
  return timestampMs(left) >= timestampMs(right) ? left : right;
}

export function minTimestamp(left: IsoTimestamp, right: IsoTimestamp): IsoTimestamp {
  return timestampMs(left) <= timestampMs(right) ? left : right;
}

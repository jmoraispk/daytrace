import type {
  ActivityRecord,
  DiagnosticCode,
  SanitizedObservation,
} from "./models.js";
import { timestampMs } from "./time.js";

const EMAIL = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const EDGE_SUFFIX = /\s+and \d+ more pages(?:\s+-.*?)?\s+-\s+Microsoft.? Edge$/i;
const SECRET = /(?:bearer\s+[A-Za-z0-9._~-]+|\b(?:api[_-]?key|access[_-]?(?:key|token)|code[_-]?challenge|session[_-]?state|password[_-]?reset|token|secret|key|code|state)\s*[=:]\s*[A-Za-z0-9._~-]{12,})/gi;
const AUTH_HOST_PARTS = ["login.", "auth.", "accounts."] as const;
const AUTH_PATH_PARTS = ["oauth", "authorize", "callback", "signin", "challenge", "recover", "reset"] as const;
const URL_HOST = "(?:localhost|\\[[0-9a-f:]+\\]|(?:\\d{1,3}\\.){3}\\d{1,3}|(?:[a-z0-9-]+\\.)+[a-z]{2,})";
const URL_TOKEN = new RegExp(`(?<![\\w@])(?:https?://)?(?:[^\\s/@]+:[^\\s/@]+@)?${URL_HOST}(?::\\d{1,5})?(?:/[^\\s]*)?`, "gi");

function urlHost(raw: string): string {
  const candidate = raw.includes("://") ? raw : `https://${raw}`;
  try {
    return new URL(candidate).hostname.replace(/^\[|\]$/g, "").toLocaleLowerCase() || "[redacted-url]";
  } catch {
    return "[redacted-url]";
  }
}

export function replaceUrlTokens(value: string): string {
  return value.replace(URL_TOKEN, (match) => urlHost(match));
}

function safePath(host?: string, path?: string): string | undefined {
  if (host === undefined || path === undefined) return undefined;
  const loweredHost = host.toLocaleLowerCase();
  const loweredPath = path.toLocaleLowerCase();
  if (
    AUTH_HOST_PARTS.some((part) => loweredHost.startsWith(part))
    || AUTH_PATH_PARTS.some((part) => loweredPath.includes(part))
  ) return undefined;
  const parts = path.split("/").filter(Boolean);
  if (loweredHost === "github.com" && parts.length >= 2) return `/${parts.slice(0, 2).join("/")}`;
  if (loweredHost.includes("gitlab") && parts.length >= 2) {
    let kept = parts.slice(0, 2);
    if (
      parts.length >= 5
      && parts[2] === "-"
      && (parts[3] === "merge_requests" || parts[3] === "jobs")
    ) kept = parts.slice(0, 5);
    return `/${kept.join("/")}`;
  }
  return undefined;
}

function safeText(value: string | undefined, diagnose?: (code: DiagnosticCode) => void): string | undefined {
  if (value === undefined || value.length === 0) return undefined;
  const normalized = value.normalize("NFKC");
  const compact = normalized.replace(/[\r\n]/g, " ").trim().split(/\s+/u).filter(Boolean).join(" ");
  const cleaned = replaceUrlTokens(compact)
    .replace(EMAIL, "[redacted-email]")
    .replace(EDGE_SUFFIX, "")
    .replace(SECRET, "[redacted-secret]");
  if (cleaned !== compact) diagnose?.("sanitized-field");
  return cleaned.slice(0, 500) || undefined;
}

export function sanitizeGeneratedText(value: string): string {
  const normalized = value.normalize("NFKC");
  const compact = normalized.replace(/[\r\n]/g, " ").trim().split(/\s+/u).filter(Boolean).join(" ");
  return replaceUrlTokens(compact)
    .replace(EMAIL, "[redacted-email]")
    .replace(SECRET, "[redacted-secret]");
}

export function containsSecret(value: string): boolean {
  return sanitizeGeneratedText(value) !== value;
}

function safePathText(value: string | undefined, diagnose: (code: DiagnosticCode) => void): string | undefined {
  const cleaned = safeText(value, diagnose);
  if (cleaned === undefined) return undefined;
  const parts = cleaned.split(/[\\/]/).filter(Boolean);
  const basename = parts.at(-1)?.replace(/^[A-Za-z]:$/, "") || undefined;
  if (basename !== cleaned) diagnose("sanitized-field");
  return basename;
}

function compareRecords(left: ActivityRecord, right: ActivityRecord): number {
  return timestampMs(left.start) - timestampMs(right.start)
    || left.bucketId.localeCompare(right.bucketId)
    || left.eventId.localeCompare(right.eventId);
}

export function sanitizeRecords(
  records: readonly ActivityRecord[],
  diagnose: (code: DiagnosticCode) => void,
): readonly SanitizedObservation[] {
  return [...records].sort(compareRecords).map((item, index) => {
    const host = item.urlHost?.toLocaleLowerCase().slice(0, 253);
    const app = safeText(item.app, diagnose);
    const title = safeText(item.title, diagnose);
    const project = safePathText(item.project, diagnose);
    const file = safePathText(item.file, diagnose);
    const urlPath = safePath(host, item.urlPath);
    const language = safeText(item.language, diagnose);
    return {
      evidenceId: `evidence-${String(index + 1).padStart(4, "0")}`,
      kind: item.kind,
      start: item.start,
      end: item.end,
      ...(app === undefined ? {} : { app }),
      ...(title === undefined ? {} : { title }),
      ...(project === undefined ? {} : { project }),
      ...(file === undefined ? {} : { file }),
      ...(host === undefined ? {} : { urlHost: host }),
      ...(urlPath === undefined ? {} : { urlPath }),
      ...(language === undefined ? {} : { language }),
    };
  });
}

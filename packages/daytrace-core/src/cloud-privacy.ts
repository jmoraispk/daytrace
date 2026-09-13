import { CloudPrivacyError } from "./models.js";
import { sanitizeGeneratedText } from "./sanitize.js";

const DIRECT_MESSAGE = /^.*?\s*\(DM\).*?(Slack|Teams).*$/i;

export function assertCloudSafePayload(value: unknown): void {
  if (typeof value === "string") {
    if (sanitizeGeneratedText(value) !== value) throw new CloudPrivacyError("unsafe-cloud-payload", "unsafe-cloud-payload");
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) assertCloudSafePayload(item);
    return;
  }
  if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      assertCloudSafePayload(key);
      assertCloudSafePayload(item);
    }
  }
}

export function minimizeCloudText(value?: string): string | undefined {
  if (!value) return undefined;
  return sanitizeGeneratedText(value).slice(0, 500) || undefined;
}

export function minimizeCloudTitle(app?: string, title?: string): string | undefined {
  if (!title) return undefined;
  const directMessage = DIRECT_MESSAGE.exec(title);
  if (directMessage?.[1] !== undefined) {
    const service = directMessage[1];
    return `Direct message - ${service[0]?.toLocaleUpperCase()}${service.slice(1).toLocaleLowerCase()}`;
  }
  const foldedApp = (app ?? "").toLocaleLowerCase();
  const foldedTitle = title.toLocaleLowerCase();
  if (foldedApp.includes("teams") || foldedTitle.includes("microsoft teams")) return "Meeting - Microsoft Teams";
  const communicationText = `${foldedApp} ${foldedTitle}`;
  if (
    communicationText.includes("outlook")
    || communicationText.includes("gmail")
    || ["mail", "thunderbird"].some((item) => foldedApp.includes(item))
  ) {
    const category = foldedTitle.includes("inbox") ? "Inbox" : foldedTitle.includes("calendar") ? "Calendar" : "Email";
    const display = communicationText.includes("outlook") ? "Outlook" : communicationText.includes("gmail") ? "Gmail" : "Mail";
    return `${category} - ${display}`;
  }
  return minimizeCloudText(title);
}

export function minimizeCloudPath(value?: string): string | undefined {
  if (!value) return undefined;
  const name = value.split(/[\\/]/u).filter(Boolean).at(-1);
  return minimizeCloudText(name);
}

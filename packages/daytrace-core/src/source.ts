import {
  ActivityWatchConnectionError,
  DaytraceInputError,
} from "./models.js";
import type {
  ActivityWatchTransport,
  IsoTimestamp,
  RawBucket,
  RawEvent,
  ServerEndpoint,
  ServerInfo,
} from "./models.js";

function objectValue(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ActivityWatchConnectionError("invalid-response", "invalid ActivityWatch response");
  }
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function rethrowConnection(error: unknown, code: string, message: string, signal?: AbortSignal): never {
  if (signal?.aborted) signal.throwIfAborted();
  if (error instanceof DOMException && error.name === "AbortError") throw error;
  throw new ActivityWatchConnectionError(code, message);
}

export function parseServerUrl(value: string): ServerEndpoint {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new DaytraceInputError("invalid-server-url", "invalid ActivityWatch server URL");
  }
  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:")
    || parsed.hostname.length === 0
    || parsed.username.length > 0
    || parsed.password.length > 0
    || parsed.pathname !== "/"
    || parsed.search.length > 0
    || parsed.hash.length > 0
  ) {
    throw new DaytraceInputError("invalid-server-url", "invalid ActivityWatch server URL");
  }
  const parsedPort = parsed.port === "" ? 5600 : Number(parsed.port);
  if (!Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535) {
    throw new DaytraceInputError("invalid-server-url", "invalid ActivityWatch server URL");
  }
  return {
    protocol: parsed.protocol.slice(0, -1) as "http" | "https",
    host: parsed.hostname,
    port: parsedPort,
  };
}

export class ActivityWatchSource {
  readonly #server: string;
  readonly #transport: ActivityWatchTransport;

  constructor(server: string, transport: ActivityWatchTransport) {
    const endpoint = parseServerUrl(server);
    const host = endpoint.host.includes(":") ? `[${endpoint.host.replace(/^\[|\]$/g, "")}]` : endpoint.host;
    this.#server = `${endpoint.protocol}://${host}:${endpoint.port}`;
    this.#transport = transport;
  }

  async getInfo(signal?: AbortSignal): Promise<ServerInfo> {
    try {
      const root = objectValue(await this.#transport.request({
        server: this.#server,
        path: "/api/0/info",
        ...(signal === undefined ? {} : { signal }),
      }));
      return { version: stringValue(root.version, "unknown"), testing: Boolean(root.testing) };
    } catch (error) {
      return rethrowConnection(error, "info-request", "ActivityWatch info request failed", signal);
    }
  }

  async listBuckets(signal?: AbortSignal): Promise<readonly RawBucket[]> {
    try {
      const root = objectValue(await this.#transport.request({
        server: this.#server,
        path: "/api/0/buckets",
        ...(signal === undefined ? {} : { signal }),
      }));
      return Object.entries(root)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([id, raw]) => {
          const bucket = objectValue(raw);
          return {
            id,
            type: stringValue(bucket.type),
            client: stringValue(bucket.client),
            hostname: stringValue(bucket.hostname),
          };
        });
    } catch (error) {
      return rethrowConnection(error, "bucket-request", "ActivityWatch bucket request failed", signal);
    }
  }

  async getEvents(
    bucketId: string,
    start: IsoTimestamp,
    end: IsoTimestamp,
    signal?: AbortSignal,
  ): Promise<readonly RawEvent[]> {
    try {
      const response = await this.#transport.request({
        server: this.#server,
        path: `/api/0/buckets/${encodeURIComponent(bucketId)}/events`,
        query: { start, end },
        ...(signal === undefined ? {} : { signal }),
      });
      if (!Array.isArray(response)) {
        throw new ActivityWatchConnectionError("invalid-response", "invalid ActivityWatch response");
      }
      return response.map((raw) => {
        const event = objectValue(raw);
        const duration = event.duration;
        const data = objectValue(event.data);
        if (typeof event.timestamp !== "string" || typeof duration !== "number" || !Number.isFinite(duration)) {
          throw new ActivityWatchConnectionError("invalid-response", "invalid ActivityWatch response");
        }
        return {
          id: String(event.id ?? ""),
          timestamp: event.timestamp,
          durationSeconds: duration,
          data: { ...data },
        };
      });
    } catch (error) {
      return rethrowConnection(error, "event-request", "ActivityWatch event request failed", signal);
    }
  }
}

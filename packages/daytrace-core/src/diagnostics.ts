import type { DiagnosticCode, DiagnosticCount } from "./models.js";

const ORDER: readonly DiagnosticCode[] = [
  "non-positive-event",
  "naive-timestamp",
  "unsupported-bucket",
  "window-conflict",
  "sanitized-field",
];

const MESSAGES: Readonly<Record<DiagnosticCode, string>> = {
  "non-positive-event": "non-positive ActivityWatch event",
  "naive-timestamp": "event with a naive timestamp",
  "unsupported-bucket": "unsupported ActivityWatch bucket",
  "window-conflict": "conflicting foreground interval",
  "sanitized-field": "captured field containing private data",
};

export class DiagnosticCollector {
  readonly #counts = new Map<DiagnosticCode, number>();

  add(code: DiagnosticCode, count = 1): void {
    if (count > 0) this.#counts.set(code, (this.#counts.get(code) ?? 0) + count);
  }

  snapshot(): readonly DiagnosticCount[] {
    return ORDER.flatMap((code) => {
      const count = this.#counts.get(code) ?? 0;
      return count > 0 ? [{ code, count }] : [];
    });
  }
}

export function diagnosticMessages(counts: readonly DiagnosticCount[]): readonly string[] {
  return counts.map(({ code, count }) => (
    `ignored ${count} ${MESSAGES[code]}${count === 1 ? "" : "s"}`
  ));
}

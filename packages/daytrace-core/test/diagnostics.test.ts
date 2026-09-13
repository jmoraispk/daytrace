import { describe, expect, it } from "vitest";

import { DiagnosticCollector, diagnosticMessages } from "../src/diagnostics.js";

describe("DiagnosticCollector", () => {
  it("aggregates in stable code order without event content", () => {
    const collector = new DiagnosticCollector();
    collector.add("sanitized-field", 2);
    collector.add("non-positive-event");
    collector.add("unsupported-bucket", 3);

    expect(collector.snapshot()).toEqual([
      { code: "non-positive-event", count: 1 },
      { code: "unsupported-bucket", count: 3 },
      { code: "sanitized-field", count: 2 },
    ]);
    expect(diagnosticMessages(collector.snapshot())).toEqual([
      "ignored 1 non-positive ActivityWatch event",
      "ignored 3 unsupported ActivityWatch buckets",
      "ignored 2 captured field containing private datas",
    ]);
    expect(JSON.stringify(collector.snapshot())).not.toContain("event-id");
  });
});

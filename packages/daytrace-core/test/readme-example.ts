import {
  collectDay,
  renderDigestMarkdown,
  renderEpisodeMarkdown,
  summarizeBundleOrFallback,
  type ActivityWatchTransport,
  type SummaryProvider,
} from "../src/index.js";

export async function documentedExample(
  transport: ActivityWatchTransport,
  provider: SummaryProvider,
  controller: AbortController,
): Promise<string> {
  const bundle = await collectDay({
    day: "2026-09-10",
    timezoneName: "Europe/Lisbon",
    transport,
    signal: controller.signal,
  });
  const result = await summarizeBundleOrFallback(bundle, provider, undefined, {
    signal: controller.signal,
  });
  return result.kind === "ai"
    ? renderDigestMarkdown(bundle, result.digest, result.provenance)
    : renderEpisodeMarkdown(result.bundle);
}

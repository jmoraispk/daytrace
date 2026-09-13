import { execFileSync } from "node:child_process";
import { builtinModules } from "node:module";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { build } from "esbuild";

const packageDirectory = dirname(dirname(fileURLToPath(import.meta.url)));
const temporaryDirectory = await mkdtemp(join(tmpdir(), "daytrace-browser-smoke-"));
const consumer = join(temporaryDirectory, "consumer");

try {
  await mkdir(consumer);
  const packed = JSON.parse(execFileSync("npm", ["pack", "--json", "--pack-destination", temporaryDirectory], {
    cwd: packageDirectory,
    encoding: "utf8",
  }));
  const tarball = join(temporaryDirectory, packed[0].filename);
  await writeFile(join(consumer, "package.json"), JSON.stringify({ private: true, type: "module" }));
  execFileSync("npm", ["install", "--ignore-scripts", "--no-audit", "--no-fund", "--no-package-lock", tarball], {
    cwd: consumer,
    stdio: "pipe",
  });
  const entry = join(consumer, "entry.mjs");
  await writeFile(entry, `import { DAYTRACE_VERSION, buildSummaryPlan, renderEpisodeJson } from "@jmoraispk/daytrace";
globalThis.__daytraceSmoke = { version: DAYTRACE_VERSION, buildSummaryPlan, renderEpisodeJson };
`);
  const installed = await import(pathToFileURL(join(consumer, "node_modules", "@jmoraispk", "daytrace", "dist", "index.js")));
  if (installed.DAYTRACE_VERSION !== "0.4.0" || typeof installed.buildSummaryPlan !== "function") {
    throw new Error("packed package exports are incomplete");
  }
  const output = join(consumer, "bundle.js");
  const result = await build({
    absWorkingDir: consumer,
    entryPoints: [entry],
    outfile: output,
    bundle: true,
    platform: "browser",
    format: "esm",
    metafile: true,
    logLevel: "silent",
  });
  const builtins = new Set([...builtinModules, ...builtinModules.map((name) => `node:${name}`)]);
  const unsafeImport = Object.values(result.metafile.outputs)
    .flatMap((item) => item.imports)
    .find((item) => item.path.startsWith("node:") || builtins.has(item.path));
  if (unsafeImport !== undefined) throw new Error(`browser bundle contains Node import: ${unsafeImport.path}`);
  if ((await readFile(output, "utf8")).includes("node:")) throw new Error("browser bundle contains a node: reference");
  process.stdout.write("Browser package smoke test passed.\n");
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}

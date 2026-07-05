#!/usr/bin/env node
/**
 * Spec-Sheet Guard — CLI entry.
 *
 * Reads a packaging spec (YAML or JSON), fetches EPR compliance pathways for every
 * market it sells into, and fails (exit 1) when an unmet, unacknowledged obligation
 * applies to the product's materials. Drop it into CI to catch a fine before tooling.
 *
 * Usage:
 *   spec-sheet-guard [--spec packaging.yaml] [--warn-only] [--json]
 *                    [--fail-window <days>] [--github]
 */
import { readFileSync, existsSync } from "node:fs";
import { parse as parseYaml } from "yaml";
import { fetchPathways, type Pathway } from "./client.js";
import { evaluate, type PackagingSpec } from "./guard.js";
import { renderText, renderGithubAnnotations } from "./format.js";

interface Args {
  spec: string;
  warnOnly: boolean;
  json: boolean;
  github: boolean;
  failWindow: number;
}

function parseArgs(argv: string[]): Args {
  const args: Args = {
    spec: "",
    warnOnly: false,
    json: false,
    github: !!process.env.GITHUB_ACTIONS,
    failWindow: Infinity,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--spec") args.spec = argv[++i] ?? "";
    else if (a === "--warn-only") args.warnOnly = true;
    else if (a === "--json") args.json = true;
    else if (a === "--github") args.github = true;
    else if (a === "--fail-window") args.failWindow = Number(argv[++i]);
    else if (a === "-h" || a === "--help") {
      console.log(
        "Usage: spec-sheet-guard [--spec packaging.yaml] [--warn-only] [--json] [--github] [--fail-window <days>]"
      );
      process.exit(0);
    }
  }
  return args;
}

function resolveSpecPath(explicit: string): string {
  if (explicit) return explicit;
  for (const c of ["packaging.yaml", "packaging.yml", "packaging.json"]) {
    if (existsSync(c)) return c;
  }
  throw new Error(
    "No spec file found. Create packaging.yaml or pass --spec <path>. See packaging.example.yaml."
  );
}

function loadSpec(path: string): PackagingSpec {
  if (!existsSync(path)) throw new Error(`Spec file not found: ${path}`);
  const raw = readFileSync(path, "utf8");
  const data = (path.endsWith(".json") ? JSON.parse(raw) : parseYaml(raw)) as Partial<PackagingSpec>;
  if (!data || !Array.isArray(data.markets) || data.markets.length === 0) {
    throw new Error(`Spec "${path}" must list at least one entry under "markets".`);
  }
  if (!Array.isArray(data.materials) || data.materials.length === 0) {
    throw new Error(`Spec "${path}" must list at least one entry under "materials".`);
  }
  return {
    product: data.product,
    markets: data.markets.map(String),
    materials: data.materials.map(String),
    acknowledged: Array.isArray(data.acknowledged) ? data.acknowledged.map(String) : [],
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const specPath = resolveSpecPath(args.spec);
  const spec = loadSpec(specPath);

  // De-dupe markets and fetch pathways for each, in parallel.
  const markets = [...new Set(spec.markets.map((m) => m.trim().toUpperCase()))];
  spec.markets = markets;
  const results = await Promise.all(
    markets.map(async (m) => [m, await fetchPathways(m)] as const)
  );
  const pathwaysByMarket: Record<string, Pathway[]> = Object.fromEntries(results);

  const report = evaluate(spec, pathwaysByMarket, { failWindowDays: args.failWindow });

  if (args.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(renderText(report));
    if (args.github) {
      const anns = renderGithubAnnotations(report);
      if (anns) console.log("\n" + anns);
    }
  }

  return report.ok || args.warnOnly ? 0 : 1;
}

// Set exitCode and let the process end on its own rather than calling process.exit():
// an abrupt exit while fetch/undici keep-alive sockets are still open trips a libuv
// assertion on Windows (async.c line 76). Graceful shutdown avoids that crash.
main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((err) => {
    console.error(`spec-sheet-guard: ${err instanceof Error ? err.message : String(err)}`);
    process.exitCode = 2;
  });

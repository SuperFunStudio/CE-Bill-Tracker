/** Standalone smoke test: spawn the built server over stdio and exercise all 5 tools. */
import assert from "node:assert";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

type ContentBlock = { type: string; text?: string };

function textOf(result: unknown): string {
  const content = ((result as { content?: ContentBlock[] }).content ?? []) as ContentBlock[];
  return content.find((c) => c.type === "text")?.text ?? "";
}

/** Spawn dist/index.js over stdio, optionally with env overrides for the child. */
async function spawnServer(envOverrides?: Record<string, string>): Promise<Client> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  Object.assign(env, envOverrides ?? {});
  const transport = new StdioClientTransport({ command: "node", args: ["dist/index.js"], env });
  const client = new Client({ name: "smoke", version: "0.0.0" });
  await client.connect(transport);
  return client;
}

async function main() {
  const client = await spawnServer();

  const tools = await client.listTools();
  const names = tools.tools.map((t) => t.name);
  console.log("TOOLS:", names.join(", "));
  for (const expected of [
    "check_compliance",
    "find_laws",
    "upcoming_deadlines",
    "coverage_matrix",
    "watch_material",
  ]) {
    assert.ok(names.includes(expected), `missing tool: ${expected}`);
  }

  // ---- 1. check_compliance (live API) -------------------------------------------------------
  const cc = await client.callTool({
    name: "check_compliance",
    arguments: { materials: ["packaging"], regions: ["US"], states: ["CO"] },
  });
  const txt = textOf(cc);
  assert.ok(txt.includes("Compliance snapshot"), "check_compliance should render a snapshot header");
  console.log("\n--- check_compliance(packaging, CO) ---\n" + txt.slice(0, 900));

  // ---- 2. find_laws (live API) ---------------------------------------------------------------
  const fl = await client.callTool({
    name: "find_laws",
    arguments: { material_category: "batteries", regions: "all", status: "enacted", limit: 3 },
  });
  const ftxt = textOf(fl);
  assert.match(ftxt, /^Found \d+ law\(s\)\./, "find_laws should report a count");
  console.log("\n--- find_laws(batteries, enacted) ---\n" + ftxt.slice(0, 500));

  // ---- 3. upcoming_deadlines (live API) ------------------------------------------------------
  const ud = await client.callTool({
    name: "upcoming_deadlines",
    arguments: { days_ahead: 365 },
  });
  const udTxt = textOf(ud);
  assert.match(udTxt, /^\d+ deadline\(s\) shown:/, "upcoming_deadlines should report a count");
  const udStruct = ud.structuredContent as { deadlines?: unknown; stats?: unknown } | undefined;
  assert.ok(udStruct && Array.isArray(udStruct.deadlines), "structuredContent.deadlines must be an array");
  for (const d of udStruct.deadlines as Array<{ deadline_date?: unknown }>) {
    assert.equal(typeof d.deadline_date, "string", "each deadline needs a deadline_date string");
  }
  console.log("\n--- upcoming_deadlines(365d) ---\n" + udTxt.slice(0, 400));

  // ---- 4. coverage_matrix (live API) ---------------------------------------------------------
  const cm = await client.callTool({ name: "coverage_matrix", arguments: {} });
  const cmTxt = textOf(cm);
  assert.ok(cmTxt.includes("Top instrument×material cells"), "coverage_matrix should render header");
  const cmStruct = cm.structuredContent as { cells?: unknown } | undefined;
  assert.ok(cmStruct && Array.isArray(cmStruct.cells), "structuredContent.cells must be an array");
  assert.ok((cmStruct.cells as unknown[]).length > 0, "matrix should have at least one cell");
  const cell = (cmStruct.cells as Array<Record<string, unknown>>)[0];
  assert.equal(typeof cell.instrument_type, "string", "cell.instrument_type must be a string");
  assert.equal(typeof cell.material_category, "string", "cell.material_category must be a string");
  assert.equal(typeof cell.count, "number", "cell.count must be a number");
  console.log("\n--- coverage_matrix(all) ---\n" + cmTxt.slice(0, 400));

  // ---- 5a. watch_material — schema rejects a bad email (no network call made) ----------------
  // NOTE: the happy path is deliberately NOT smoke-tested — it would create a real email
  // subscription against the prod API (and POST /subscriptions is rate-limited to 12/min).
  // Instead we verify (a) input validation rejects junk before any request is sent, and
  // (b) the error path returns a graceful tool error rather than crashing the server.
  let badEmailRejected = false;
  try {
    const res = await client.callTool({
      name: "watch_material",
      arguments: { email: "not-an-email" },
    });
    // Some SDK versions surface validation failures as an isError result instead of throwing.
    badEmailRejected = res.isError === true;
  } catch {
    badEmailRejected = true; // thrown MCP invalid-params error — also fine
  }
  assert.ok(badEmailRejected, "watch_material must reject an invalid email address");
  console.log("\n--- watch_material(bad email) --- rejected as expected");

  await client.close();

  // ---- 5b. watch_material — API-failure path via an unreachable base URL ---------------------
  // A second server instance pointed at a dead endpoint: the subscribe call fails fast and the
  // tool must return an error content block ("❌ Subscription failed: …"), not an unhandled
  // rejection that kills the process.
  const deadClient = await spawnServer({
    SIGNALSCOUT_API_BASE_URL: "http://127.0.0.1:9", // discard port — nothing listens here
  });
  const wm = await deadClient.callTool({
    name: "watch_material",
    arguments: { email: "smoke-test@example.com", materials: ["packaging"] },
  });
  const wmTxt = textOf(wm);
  assert.equal(wm.isError, true, "watch_material against a dead API must return isError");
  assert.ok(
    wmTxt.startsWith("❌ Subscription failed:"),
    `watch_material error text should start with "❌ Subscription failed:", got: ${wmTxt.slice(0, 120)}`
  );
  console.log("\n--- watch_material(dead API) ---\n" + wmTxt.slice(0, 200));
  await deadClient.close();

  console.log("\nSMOKE_OK");
}

main().catch((e) => {
  console.error("SMOKE_FAIL", e);
  process.exit(1);
});

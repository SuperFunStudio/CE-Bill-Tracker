#!/usr/bin/env node
/**
 * Compliance Copilot — an MCP server over the public SignalScout API.
 *
 * Hackathon reference implementation. It exposes the SignalScout EPR / circular-economy
 * dataset as a handful of LLM-callable tools so any MCP client (Claude Desktop, Claude Code,
 * Cursor, …) can answer "what are my Extended Producer Responsibility obligations?" for a
 * given product, material, and set of jurisdictions — and subscribe to alerts when the law
 * changes.
 *
 * Run:  node dist/index.js   (stdio transport)
 * Config: SIGNALSCOUT_API_BASE_URL (defaults to prod), SIGNALSCOUT_API_TOKEN (optional Pro seat).
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { API_BASE, client, type Pathway } from "./client.js";

const server = new McpServer({
  name: "compliance-copilot",
  version: "0.1.0",
});

/** Normalize a region token to the API's convention (US, EU, FR, JP, …). "all" passes through. */
function normRegion(r: string): string {
  const t = r.trim().toLowerCase();
  if (t === "all") return "all";
  return t.toUpperCase();
}

function overlaps(a: string[] | null | undefined, b: string[]): boolean {
  if (!b.length) return true; // no material filter = everything
  if (!a) return false;
  const set = new Set(a.map((s) => s.toLowerCase()));
  return b.some((m) => set.has(m.toLowerCase()));
}

/** Gather compliance pathways across the requested regions/states, then filter by material. */
async function gatherPathways(
  materials: string[],
  regions: string[],
  states: string[],
): Promise<Pathway[]> {
  const calls: Promise<Pathway[]>[] = [];
  const usStates = states.map((s) => s.toUpperCase());
  const wantsAll = regions.includes("all");
  const wantsUS = wantsAll || regions.includes("US");

  if (usStates.length && wantsUS) {
    for (const st of usStates) calls.push(client.pathways({ region: "US", state: st }));
  } else if (regions.length) {
    for (const r of regions) calls.push(client.pathways({ region: r }));
  } else {
    calls.push(client.pathways({ region: "all" }));
  }

  const settled = await Promise.allSettled(calls);
  const seen = new Set<number>();
  const out: Pathway[] = [];
  for (const s of settled) {
    if (s.status !== "fulfilled") continue;
    for (const p of s.value) {
      if (seen.has(p.bill_id)) continue;
      if (!overlaps(p.material_categories, materials)) continue;
      seen.add(p.bill_id);
      out.push(p);
    }
  }
  // Soonest real deadline first; nulls last.
  out.sort((a, b) => {
    if (a.next_deadline_date === b.next_deadline_date) return 0;
    if (!a.next_deadline_date) return 1;
    if (!b.next_deadline_date) return -1;
    return a.next_deadline_date < b.next_deadline_date ? -1 : 1;
  });
  return out;
}

// --------------------------------------------------------------------------------------------
// Tool 1 (flagship): check_compliance — product/material + jurisdictions -> obligations report
// --------------------------------------------------------------------------------------------
server.registerTool(
  "check_compliance",
  {
    title: "Check EPR compliance obligations",
    description:
      "Given the materials in a product (e.g. packaging, electronics, batteries, textiles, paper, " +
      "glass) and the jurisdictions it is sold in (US state codes and/or regions like EU), return the " +
      "actionable Extended Producer Responsibility obligations: which producer responsibility " +
      "organization (PRO) to join or plan to file, the registration link, the next deadline, and " +
      "whether fees apply. This is the 'am I compliant?' entry point.",
    inputSchema: {
      materials: z
        .array(z.string())
        .describe("Material/product categories, e.g. ['packaging','electronics']. Empty = all materials."),
      regions: z
        .array(z.string())
        .default(["all"])
        .describe("Region codes: 'US', 'EU', 'FR', 'JP', or 'all'. Defaults to all."),
      states: z
        .array(z.string())
        .default([])
        .describe("Optional US state codes to narrow to, e.g. ['CA','OR','CO']."),
    },
  },
  async ({ materials, regions, states }) => {
    const mats = materials ?? [];
    const regs = (regions ?? ["all"]).map(normRegion);
    const sts = states ?? [];

    const [pathways, deadlineStats] = await Promise.all([
      gatherPathways(mats, regs, sts),
      client
        .deadlinesSummary({
          days_ahead: 1095,
          region: regs.includes("all") ? "all" : regs[0],
          materials: mats.join(",") || undefined,
          states: sts.join(",") || undefined,
        })
        .catch(() => null),
    ]);

    const actionable = pathways.filter((p) => p.action_type !== "monitor");
    const lines: string[] = [];
    const scope = `${mats.length ? mats.join(", ") : "all materials"} · ${
      sts.length ? sts.join(", ") : regs.join(", ")
    }`;
    lines.push(`# Compliance snapshot — ${scope}`);
    if (deadlineStats) {
      lines.push(
        `\n**Deadline pressure:** ${deadlineStats.total_upcoming} upcoming · ${deadlineStats.within_30} within 30 days · ` +
          `${deadlineStats.within_90} within 90 days` +
          (deadlineStats.next_date ? ` · nearest ${deadlineStats.next_date}` : ""),
      );
    }
    lines.push(`\n**${actionable.length} obligation(s)** requiring action (plus ${pathways.length - actionable.length} to monitor).\n`);

    for (const p of pathways) {
      const flag = p.action_type === "monitor" ? "👀" : "✅";
      const fee = p.has_fee ? " · 💲 fees apply" : "";
      const due = p.next_deadline_date ? ` · ⏰ due ${p.next_deadline_date}` : "";
      lines.push(`## ${flag} ${p.bill_number} — ${p.bill_title}`);
      lines.push(`- **Materials:** ${(p.material_categories ?? []).join(", ") || "n/a"}`);
      lines.push(`- **Action:** \`${p.action_type}\` — ${p.action_summary}${fee}${due}`);
      if (p.entity) {
        lines.push(
          `- **Who:** ${p.entity.name} (${p.entity.entity_type})` +
            (p.entity.registration_url ? ` → ${p.entity.registration_url}` : p.entity.url ? ` → ${p.entity.url}` : ""),
        );
      } else if (p.registration_url) {
        lines.push(`- **Register:** ${p.registration_url}`);
      }
      lines.push("");
    }

    if (!pathways.length) {
      lines.push("_No enacted EPR obligations found for that material/jurisdiction combination yet. Use `watch_material` to get alerted when one lands._");
    }

    // Honesty note: the public API currently serves fully-populated compliance pathways for US
    // states. Non-US regions are in the data model but their pathway layer / region filtering
    // activate when the multi-region API is deployed — until then a non-US, non-state query is
    // answered from the US-scoped pathway set.
    const nonUsRegion = regs.some((r) => r !== "US" && r !== "all");
    if (nonUsRegion && !sts.length) {
      lines.push(
        "\n> ⚠️ Populated compliance-pathway data is currently US-state-scoped on the public API. " +
          "For US, pass `states` (e.g. ['CA']) for precise results; non-US regions are region-ready but not yet populated.",
      );
    }

    return {
      content: [{ type: "text", text: lines.join("\n") }],
      structuredContent: { pathways, deadlineStats, scope },
    };
  },
);

// --------------------------------------------------------------------------------------------
// Tool 2: find_laws — search / filter the underlying bill dataset
// --------------------------------------------------------------------------------------------
server.registerTool(
  "find_laws",
  {
    title: "Find circular-economy laws & bills",
    description:
      "Search the SignalScout dataset of EPR / circular-economy legislation. Filter by material, " +
      "instrument type (epr, eco_modulation, recycled_content, labeling, disposal_ban, right_to_repair, " +
      "incentives, …), jurisdiction, and status (introduced/enacted). Returns matching laws with their " +
      "official source URL.",
    inputSchema: {
      material_category: z.string().optional().describe("Single material, e.g. 'batteries'."),
      instrument_type: z.string().optional().describe("Policy instrument slug, e.g. 'epr'."),
      regions: z.string().optional().describe("CSV of region codes, e.g. 'US,EU'. Omit or 'all' for every region."),
      state: z.string().optional().describe("US state code, e.g. 'CA'."),
      status: z.string().optional().describe("'enacted' or 'introduced'."),
      limit: z.number().int().min(1).max(100).default(25),
    },
  },
  async (args) => {
    const bills = await client.bills({
      material_category: args.material_category,
      instrument_type: args.instrument_type,
      regions: args.regions ?? "all",
      state: args.state,
      status: args.status,
      ce_relevant: true,
      limit: args.limit ?? 25,
    });
    const rows = bills.map((b) => {
      const loc = b.state || b.region;
      return `- **${b.bill_number}** (${loc}, ${b.status ?? "?"}) — ${b.title}` +
        `\n   instrument: ${b.instrument_type ?? "n/a"} · materials: ${(b.material_categories ?? []).join(", ") || "n/a"}` +
        (b.source_url ? `\n   source: ${b.source_url}` : "");
    });
    const header = `Found ${bills.length} law(s).`;
    return {
      content: [{ type: "text", text: `${header}\n\n${rows.join("\n")}` }],
      structuredContent: { count: bills.length, bills },
    };
  },
);

// --------------------------------------------------------------------------------------------
// Tool 3: upcoming_deadlines — the compliance calendar
// --------------------------------------------------------------------------------------------
server.registerTool(
  "upcoming_deadlines",
  {
    title: "Upcoming compliance deadlines",
    description:
      "List upcoming EPR compliance deadlines (registration, plan-filing, reporting, fee dates), " +
      "optionally scoped to specific materials and US states. Note: the free tier returns the soonest " +
      "few deadlines; set SIGNALSCOUT_API_TOKEN to a Pro seat for the full calendar.",
    inputSchema: {
      days_ahead: z.number().int().min(1).max(1825).default(180),
      materials: z.string().optional().describe("CSV of materials, e.g. 'packaging,electronics'."),
      states: z.string().optional().describe("CSV of US state codes, e.g. 'CA,OR'."),
      region: z.string().optional().describe("'US' (default), 'EU', or 'all'."),
    },
  },
  async (args) => {
    const [rows, stats] = await Promise.all([
      client.deadlinesUpcoming({
        days_ahead: args.days_ahead ?? 180,
        materials: args.materials,
        states: args.states,
        region: args.region,
      }),
      client
        .deadlinesSummary({
          days_ahead: Math.max(args.days_ahead ?? 180, 1095),
          materials: args.materials,
          states: args.states,
          region: args.region,
        })
        .catch(() => null),
    ]);
    const list = rows
      .map((d) => `- **${d.deadline_date}** — ${d.bill_title ?? d.label ?? "deadline"}${d.state ? ` (${d.state})` : ""}`)
      .join("\n");
    const summary = stats
      ? `\n\n_${stats.total_upcoming} total upcoming · ${stats.within_30} within 30d · ${stats.within_90} within 90d._`
      : "";
    return {
      content: [{ type: "text", text: `${rows.length} deadline(s) shown:\n\n${list}${summary}` }],
      structuredContent: { deadlines: rows, stats },
    };
  },
);

// --------------------------------------------------------------------------------------------
// Tool 4: coverage_matrix — where regulation is dense (instrument x material)
// --------------------------------------------------------------------------------------------
server.registerTool(
  "coverage_matrix",
  {
    title: "Regulation coverage matrix",
    description:
      "Counts of EPR-relevant laws per (policy instrument × material category), optionally by region. " +
      "Useful for spotting where regulation is dense vs. emerging.",
    inputSchema: {
      regions: z.string().optional().describe("CSV of region codes or 'all' (default)."),
    },
  },
  async (args) => {
    const cells = await client.matrix({ regions: args.regions ?? "all" });
    cells.sort((a, b) => b.count - a.count);
    const top = cells
      .slice(0, 30)
      .map((c) => `- ${c.instrument_type} × ${c.material_category}${c.region ? ` (${c.region})` : ""}: **${c.count}**`)
      .join("\n");
    return {
      content: [{ type: "text", text: `Top instrument×material cells:\n\n${top}` }],
      structuredContent: { cells },
    };
  },
);

// --------------------------------------------------------------------------------------------
// Tool 5: watch_material — subscribe to alerts when the law changes
// --------------------------------------------------------------------------------------------
server.registerTool(
  "watch_material",
  {
    title: "Subscribe to compliance alerts",
    description:
      "Create an email alert subscription so the user is notified when new EPR / circular-economy laws " +
      "affecting their materials and jurisdictions are detected. Confirm the email address with the user " +
      "before calling.",
    inputSchema: {
      email: z.string().email().describe("Subscriber email address."),
      organization: z.string().optional(),
      materials: z.array(z.string()).default([]).describe("Material categories to watch; empty = all."),
      region_scope: z
        .record(z.array(z.string()))
        .optional()
        .describe("Region -> jurisdiction list, e.g. {\"US\":[\"CA\",\"OR\"],\"EU\":[\"*\"]}. '*' = whole region."),
      instrument_types: z
        .array(z.string())
        .default(["ALL"])
        .describe("Instrument slugs to watch, or ['ALL'] for every topic."),
    },
  },
  async (args) => {
    // The API can reject this (validation 400s, and POST /subscriptions is rate-limited to
    // 12/min) — surface that as a tool error instead of crashing with an unhandled rejection.
    try {
      await client.subscribe({
        email: args.email,
        organization: args.organization,
        region_scope: args.region_scope,
        instrument_types: args.instrument_types?.length ? args.instrument_types : ["ALL"],
        material_categories: args.materials?.length ? args.materials : undefined,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return {
        content: [{ type: "text", text: `❌ Subscription failed: ${message}` }],
        isError: true,
      };
    }
    return {
      content: [
        {
          type: "text",
          text: `✅ Subscribed ${args.email} to alerts for ${
            args.materials?.length ? args.materials.join(", ") : "all materials"
          }. They'll be notified when matching laws change.`,
        },
      ],
    };
  },
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stderr is safe for logs; stdout is the MCP channel.
  console.error(`compliance-copilot MCP server ready → ${API_BASE}`);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});

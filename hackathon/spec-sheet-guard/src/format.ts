/** Rendering: a human-readable report for terminals + GitHub Actions annotations. */
import type { Finding, GuardReport, Severity } from "./guard.js";

const ICON: Record<Severity, string> = { error: "✗", warning: "!", note: "·" };

function deadlineLabel(f: Finding): string {
  if (f.deadline === null) return "no deadline set";
  if (f.daysToDeadline === null) return f.deadline;
  if (f.daysToDeadline < 0) return `${f.deadline} — OVERDUE by ${-f.daysToDeadline}d`;
  return `${f.deadline} — in ${f.daysToDeadline}d`;
}

export function renderText(report: GuardReport): string {
  const { spec, findings, counts, ok } = report;
  const lines: string[] = [];
  const product = spec.product ? ` — ${spec.product}` : "";
  lines.push(`Spec-Sheet Guard${product}`);
  lines.push(`markets: ${spec.markets.join(", ")}   materials: ${spec.materials.join(", ")}`);
  lines.push("");

  if (findings.length === 0) {
    lines.push("No EPR obligations found for these materials in these markets.");
  }

  for (const f of findings) {
    const ack = f.acknowledged ? " [acknowledged]" : "";
    const fee = f.hasFee ? " 💲fee" : "";
    lines.push(
      `${ICON[f.severity]} ${f.severity.toUpperCase()}  ${f.market}  ${f.billNumber} — ${f.billTitle}${ack}`
    );
    lines.push(`    action: ${f.actionType} — ${f.actionSummary}`);
    if (f.entityName) lines.push(`    register with: ${f.entityName}${fee}`);
    if (f.matchedMaterials.length) lines.push(`    materials: ${f.matchedMaterials.join(", ")}`);
    lines.push(`    deadline: ${deadlineLabel(f)}`);
    if (f.severity === "error" && f.registrationUrl) lines.push(`    → ${f.registrationUrl}`);
    lines.push("");
  }

  lines.push(
    `Summary: ${counts.error} error, ${counts.warning} warning, ${counts.note} note` +
      (counts.acknowledged ? ` (${counts.acknowledged} acknowledged)` : "")
  );
  lines.push(
    ok
      ? "PASS — no unmet obligations block this spec."
      : `FAIL — ${counts.error} unmet obligation(s). Register, or add to \`acknowledged\` once handled.`
  );
  return lines.join("\n");
}

/** GitHub Actions workflow commands so findings surface as PR annotations. */
export function renderGithubAnnotations(report: GuardReport): string {
  const out: string[] = [];
  for (const f of report.findings) {
    if (f.severity === "note") continue;
    const cmd = f.severity === "error" ? "error" : "warning";
    const title = `EPR ${f.market} ${f.billNumber}`;
    const msg =
      `${f.actionType}: ${f.actionSummary}` +
      (f.entityName ? ` (register with ${f.entityName})` : "") +
      ` — deadline ${deadlineLabel(f)}`;
    out.push(`::${cmd} title=${title}::${msg.replace(/\r?\n/g, " ")}`);
  }
  return out.join("\n");
}

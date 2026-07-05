/** Minimal zero-dep test of the pure evaluation core. Run: npm test (after build). */
import assert from "node:assert";
import { evaluate, type PackagingSpec } from "./guard.js";
import type { Pathway } from "./client.js";

function pathway(over: Partial<Pathway>): Pathway {
  return {
    bill_id: 1,
    bill_number: "SB-1",
    bill_title: "Test law",
    material_categories: ["plastic_packaging"],
    management_model: "pro_single",
    action_type: "join_pro",
    action_summary: "Join the PRO.",
    registration_url: "https://example.org/register",
    next_deadline_date: "2026-09-30",
    has_fee: true,
    entity: { slug: "caa", name: "CircularAction Alliance", entity_type: "pro" },
    ...over,
  };
}

const spec: PackagingSpec = {
  product: "Test",
  markets: ["CA"],
  materials: ["plastic_packaging"],
};

const TODAY = "2026-07-01";

// 1. An actionable, material-matching, unacknowledged obligation is an ERROR that blocks.
{
  const r = evaluate(spec, { CA: [pathway({})] }, { today: TODAY });
  assert.equal(r.counts.error, 1, "actionable obligation should be an error");
  assert.equal(r.ok, false, "build should fail");
  assert.equal(r.findings[0].daysToDeadline, 91, "deadline math (Jul 1 -> Sep 30)");
}

// 2. Acknowledging it (by entity name) downgrades to a passing note — and matching is
//    tolerant of spacing/punctuation, so the real-world name "Circular Action Alliance"
//    matches the API's "CircularAction Alliance".
{
  const r = evaluate(
    { ...spec, acknowledged: ["Circular Action Alliance"] },
    { CA: [pathway({})] },
    { today: TODAY }
  );
  assert.equal(r.counts.error, 0, "acknowledged obligation must not error");
  assert.equal(r.ok, true, "build should pass once acknowledged");
  assert.equal(r.findings[0].acknowledged, true);
}

// 2b. More spacing/punctuation variants of the entity name all match.
for (const variant of ["CircularAction Alliance", "circular-action-alliance", "  CIRCULAR ACTION ALLIANCE  "]) {
  const r = evaluate({ ...spec, acknowledged: [variant] }, { CA: [pathway({})] }, { today: TODAY });
  assert.equal(r.findings[0].acknowledged, true, `variant should acknowledge: "${variant}"`);
  assert.equal(r.ok, true, `build should pass for variant: "${variant}"`);
}

// 2c. Slug, bill-number, and market-scoped forms still acknowledge (with variants too).
for (const ack of ["caa", "SB-1", "sb 1", "CA:SB-1", "ca:sb-1"]) {
  const r = evaluate({ ...spec, acknowledged: [ack] }, { CA: [pathway({})] }, { today: TODAY });
  assert.equal(r.findings[0].acknowledged, true, `form should acknowledge: "${ack}"`);
}

// 2d. A market-scoped ack for a DIFFERENT market must not match, and unrelated names don't match.
for (const ack of ["OR:SB-1", "Some Other PRO"]) {
  const r = evaluate({ ...spec, acknowledged: [ack] }, { CA: [pathway({})] }, { today: TODAY });
  assert.equal(r.findings[0].acknowledged, false, `must NOT acknowledge via: "${ack}"`);
  assert.equal(r.ok, false, `build should still fail with only: "${ack}"`);
}

// 3. "monitor" / "none" actions never block.
{
  const r = evaluate(spec, { CA: [pathway({ action_type: "monitor" })] }, { today: TODAY });
  assert.equal(r.counts.error, 0, "monitor is informational");
  assert.equal(r.ok, true);
}

// 4. A law for materials we don't use is skipped entirely.
{
  const r = evaluate(spec, { CA: [pathway({ material_categories: ["batteries"] })] }, { today: TODAY });
  assert.equal(r.findings.length, 0, "non-matching materials are ignored");
}

// 5. Loose match: spec "packaging" matches "plastic_packaging".
{
  const r = evaluate({ ...spec, materials: ["packaging"] }, { CA: [pathway({})] }, { today: TODAY });
  assert.equal(r.findings.length, 1, "loose material match should fire");
}

// 6. fail-window: a far-off deadline becomes a warning, not an error.
{
  const r = evaluate(spec, { CA: [pathway({ next_deadline_date: "2027-12-31" })] }, {
    today: TODAY,
    failWindowDays: 90,
  });
  assert.equal(r.counts.error, 0, "deadline beyond window is a warning");
  assert.equal(r.counts.warning, 1);
  assert.equal(r.ok, true);
}

// 7. Unknown-material pathway in a sold-into market is a warning (review), not silent.
{
  const r = evaluate(spec, { CA: [pathway({ material_categories: null })] }, { today: TODAY });
  assert.equal(r.counts.warning, 1, "unknown-material law should warn");
  assert.equal(r.ok, true);
}

console.log("guard.test: all assertions passed ✓");

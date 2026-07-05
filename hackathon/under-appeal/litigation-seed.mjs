// Under Appeal — grounded litigation seed.
//
// The SignalScout litigation feed (/bills/{id}/litigation-cases) is fully built —
// model, CourtListener webhook, preemption_risk scoring — but prod hasn't ingested
// cases yet (the feed returns [] today). Rather than invent dockets, this file carries
// REAL, publicly-reported EPR court challenges, each cited, shaped to the exact
// LitigationCaseSummary schema the API returns. The server prefers live rows and only
// overlays these when the live feed is empty for a bill — clearly labelled source:"seed".
//
// The moment `scripts/seed_courtlistener.py` runs against prod, the live rows win and
// this overlay goes dark on its own. Field names mirror app/schemas.py:LitigationCaseSummary
// so a live row and a seed row render identically.
//
// Facts below are drawn from law-firm advisories and trade press (sources[] on each case).
// Where only the month of an event is public, filed_label carries the month and the exact
// date field is left null rather than fabricated to a day.

// challenge_type  : dormant_commerce_clause | preemption | due_process | nondelegation | other
// plaintiff_type  : industry_group | state_ags | advocacy_group | company | unknown
// case_status     : active | injunction_granted | injunction_denied | terminated
// direction       : strike (kill/pause the law) | tighten (force stricter rules) — Under Appeal's
//                   own read: a suit that wants the regs *stronger* is not a threat to your obligation.
// preemption_risk : 0–100, the API's own field — risk the related law stops being enforced.

export const SEED_CASES = [
  {
    // THE bellwether. First time a US federal court paused an EPR statute on constitutional grounds.
    courtlistener_id: null,
    case_name: 'National Association of Wholesaler-Distributors v. Feldon',
    docket_number: null,
    court_id: 'ord',
    court_name: 'U.S. District Court, D. Oregon',
    assigned_judge: 'Hon. Michael H. Simon',
    date_filed: null,
    filed_label: 'Filed July 2025',
    date_terminated: null,
    case_status: 'injunction_granted',
    challenge_type: 'dormant_commerce_clause',
    theories: ['Dormant Commerce Clause', 'Due Process', 'Non-delegation'],
    plaintiff_type: 'industry_group',
    key_plaintiffs: ['National Association of Wholesaler-Distributors'],
    related_law_id: 72452, // OR SB-582 — Plastic Pollution & Recycling Modernization Act (RMA)
    related_state: 'OR',
    related_statute: 'OR Recycling Modernization Act (SB 582)',
    preemption_risk: 86,
    direction: 'strike',
    last_activity_date: '2026-02-06',
    cl_url: null,
    events: [
      { event_type: 'filing', date_filed: null, date_label: 'Jul 2025', significance: 'high',
        summary: 'NAW sues Oregon DEQ, arguing the RMA unconstitutionally sweeps wholesalers/distributors into "producer" fees for packaging they neither design nor control.' },
      { event_type: 'injunction_motion', date_filed: null, date_label: 'Late 2025', significance: 'high',
        summary: 'Motion for preliminary injunction — NAW argues the RMA discriminates against interstate commerce and denies due process.' },
      { event_type: 'injunction_ruling', date_filed: '2026-02-06', date_label: 'Feb 6, 2026', significance: 'critical',
        summary: 'GRANTED. Judge Simon finds NAW raised "serious questions" under the Dormant Commerce Clause and Due Process, and bars DEQ from enforcing the RMA against NAW members. First federal court to pause an EPR law on constitutional grounds.' },
      { event_type: 'order', date_filed: '2026-07-13', date_label: 'Trial set Jul 13, 2026', significance: 'high',
        summary: 'Case set for trial — the merits ruling other EPR states are watching as a bellwether.' },
    ],
    sources: [
      { label: 'Waste Dive — PI granted', url: 'https://www.wastedive.com/news/national-association-wholesalers-secures-preliminary-injunction-oregon-packaging-epr-law/811723/' },
      { label: 'DLA Piper advisory', url: 'https://www.dlapiper.com/en-us/insights/publications/2026/02/oregon-epr-district-court-issues-preliminary-injunction' },
      { label: 'McGuireWoods — NAW v. Feldon', url: 'https://www.mcguirewoods.com/client-resources/alerts/2026/2/federal-court-partially-enjoins-oregons-recycling-modernization-act-in-constitutional-challenge/' },
    ],
  },
  {
    // The one that can reprice half the board: 17 state AGs + NAW vs. California SB-54.
    courtlistener_id: null,
    case_name: 'State of Nebraska et al. v. Heller et al.',
    docket_number: '2:26-at-01047',
    court_id: 'caed',
    court_name: 'U.S. District Court, E.D. California',
    assigned_judge: null,
    date_filed: '2026-06-22',
    filed_label: 'Filed Jun 22, 2026',
    date_terminated: null,
    case_status: 'active',
    challenge_type: 'dormant_commerce_clause',
    theories: ['Commerce Clause', 'First Amendment', 'U.S. & CA Constitutions'],
    plaintiff_type: 'state_ags',
    key_plaintiffs: ['17 state attorneys general (Nebraska, Texas, Florida, Georgia, Iowa, Louisiana, Missouri, Montana, +9)', 'National Association of Wholesaler-Distributors'],
    related_law_id: 865, // CA SB-54
    related_state: 'CA',
    related_statute: 'CA SB-54 — Plastic Pollution Prevention & Packaging Producer Responsibility Act',
    preemption_risk: 68,
    direction: 'strike',
    last_activity_date: '2026-06-22',
    cl_url: null,
    events: [
      { event_type: 'filing', date_filed: '2026-06-22', date_label: 'Jun 22, 2026', significance: 'critical',
        summary: '17-state coalition led by Nebraska, joined by NAW as sole business plaintiff, sues to block SB-54 as "unprecedented overreach" — Commerce Clause + First Amendment. Rides the Oregon injunction as tailwind.' },
    ],
    sources: [
      { label: 'Packaging Dive — 17 AGs sue', url: 'https://www.packagingdive.com/news/state-attorneys-general-lawsuit-california-sb54-nebraska-national-association-wholesalers/823414/' },
      { label: 'Environmental Law & Policy Monitor', url: 'https://www.environmentallawandpolicy.com/2026/06/multistate-coalition-challenge-to-californias-packaging-epr-law-raises-stakes-for-producers/' },
    ],
  },
  {
    // The nuance case: greens suing to make SB-54 STRICTER, not to kill it. Not a threat to
    // your obligation — a signal your fees may rise. Under Appeal flags direction, not just risk.
    courtlistener_id: null,
    case_name: 'NRDC, Californians Against Waste Foundation & Oceana v. CalRecycle',
    docket_number: null,
    court_id: '',
    court_name: 'California Superior Court',
    assigned_judge: null,
    date_filed: '2026-06-02',
    filed_label: 'Filed Jun 2, 2026',
    date_terminated: null,
    case_status: 'active',
    challenge_type: 'other',
    theories: ['Regulations too weak / inconsistent with SB-54'],
    plaintiff_type: 'advocacy_group',
    key_plaintiffs: ['Natural Resources Defense Council', 'Californians Against Waste Foundation', 'Oceana'],
    related_law_id: 865, // CA SB-54
    related_state: 'CA',
    related_statute: 'CA SB-54 final regulations (May 2026)',
    preemption_risk: 8,
    direction: 'tighten',
    last_activity_date: '2026-06-02',
    cl_url: null,
    events: [
      { event_type: 'filing', date_filed: '2026-06-02', date_label: 'Jun 2, 2026', significance: 'medium',
        summary: 'Environmental groups challenge the FINAL SB-54 regulations as "weakened" with "giant loopholes." Aim is stricter rules — this pushes your obligation up, not away.' },
    ],
    sources: [
      { label: 'Proskauer — EPR packaging update', url: 'https://www.proskauer.com/alert/extended-producer-responsibility-packaging-law-update' },
      { label: 'OFW Law — SB-54 litigation', url: 'https://ofwlaw.com/california-sb-54-litigation-signals-changes-for-extended-producer-responsibility-epr-packaging-compliance' },
    ],
  },
  {
    // Colorado — a narrower structural challenge (who runs the PRO), not a facial kill shot.
    courtlistener_id: null,
    case_name: 'Independent Lubricant Manufacturers Association v. Colo. Dept. of Public Health & Environment',
    docket_number: null,
    court_id: '',
    court_name: 'Denver District Court (CO)',
    assigned_judge: null,
    date_filed: '2026-03-12',
    filed_label: 'Filed Mar 12, 2026',
    date_terminated: null,
    case_status: 'active',
    challenge_type: 'nondelegation',
    theories: ['Improper approval of a second PRO'],
    plaintiff_type: 'industry_group',
    key_plaintiffs: ['Independent Lubricant Manufacturers Association'],
    related_law_id: null, // CO Producer Responsibility Program for Statewide Recycling (HB22-1355) — not in the tracked set
    related_state: 'CO',
    related_statute: 'CO Producer Responsibility Program for Statewide Recycling (HB22-1355)',
    preemption_risk: 34,
    direction: 'strike',
    last_activity_date: '2026-03-12',
    cl_url: null,
    events: [
      { event_type: 'filing', date_filed: '2026-03-12', date_label: 'Mar 12, 2026', significance: 'medium',
        summary: 'ILMA alleges CDPHE unlawfully created a second PRO by approving an individual program plan — a structural fight over how the program is run, not whether it survives.' },
    ],
    sources: [
      { label: 'Pillsbury — CO EPR challenge', url: 'https://www.pillsburylaw.com/en/news-and-insights/colorado-packaging-extended-producer-responsibility-program-lubricant-trade-association.html' },
      { label: 'Faegre Drinker — OR & CO trade-group suits', url: 'https://www.faegredrinker.com/en/insights/publications/2026/4/trade-group-lawsuits-challenge-extended-producer-responsibility-epr-laws-in-oregon-and-colorado' },
    ],
  },
];

// Index seed cases by the SignalScout bill id they attach to.
export function seedCasesByLaw(billId) {
  return SEED_CASES.filter((c) => c.related_law_id === billId);
}

// The precedent read the raw API can't give you: has the Dormant Commerce Clause theory
// actually WON against a packaging-EPR law anywhere? If so, every other state's packaging
// law stands on the same contested ground, whether or not it's been sued yet.
export function dccPrecedent() {
  const win = SEED_CASES.find(
    (c) => c.challenge_type === 'dormant_commerce_clause' && c.case_status === 'injunction_granted',
  );
  return win
    ? { case_name: win.case_name, state: win.related_state, date: win.last_activity_date,
        statute: win.related_statute }
    : null;
}

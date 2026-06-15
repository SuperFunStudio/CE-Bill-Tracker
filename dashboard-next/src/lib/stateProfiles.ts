// Curated, editorial "beyond the bills" facts per state — the home for circular-economy
// activity that isn't a tracked bill: sovereign-wealth / permanent-fund investment, standing
// agency incentive programs, and (eventually) the NREL AFDC alternative-fuel / EV / battery
// incentives that overlap our scope in certain states.
//
// This is a hand-maintained content layer, deliberately in code (typed, reviewable in a PR)
// rather than the bills DB — these records have no LegiScan/OpenStates id and aren't legislation.
// Each entry SHOULD carry a `url` to an authoritative source before it goes out; entries flagged
// with a TODO are seeded from internal knowledge and need a citation added.

export type StateProgramKind = 'fund' | 'incentive' | 'program' | 'initiative';

export interface StateProgram {
  title: string;
  /** Coarse bucket, drives the little label chip. */
  kind: StateProgramKind;
  summary: string;
  /** Authoritative source link. Required before publishing an entry. */
  url?: string;
  /** Attribution — issuing agency, fund, or dataset (e.g. "NREL AFDC"). */
  source?: string;
}

export const PROGRAM_KIND_LABEL: Record<StateProgramKind, string> = {
  fund: 'Fund',
  incentive: 'Incentive',
  program: 'Program',
  initiative: 'Initiative',
};

export const STATE_PROGRAMS: Record<string, StateProgram[]> = {
  NM: [
    {
      title: 'Permanent (sovereign-wealth) fund investment in circular infrastructure',
      kind: 'fund',
      summary:
        'New Mexico is directing a portion of its permanent / sovereign-wealth funds toward ' +
        'circular-economy infrastructure — a financing lever that sits outside the bill pipeline ' +
        'but shapes what actually gets built in-state.',
      // TODO(editorial): add the specific fund/program name + an authoritative source URL before publishing.
    },
  ],
};

export function programsForState(abbr: string): StateProgram[] {
  return STATE_PROGRAMS[abbr.toUpperCase()] ?? [];
}

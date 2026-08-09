'use client';
/**
 * The "Ask the Atlas" research engine + rendering, extracted so the unified Explore surface (the home
 * page) can host it alongside the faceted bill browse. A natural-language question over the extracted
 * corpus: the answer is grounded in retrieved bills + SQL aggregates server-side (numbers exact, claims
 * cited); this module drives the request state and renders the result. Access gating (anon: one free
 * question then sign-in; signed-in free: upgrade) is enforced server-side and mirrored here.
 *
 * useResearch()   — the ask state machine (turns, session, relevant-bills paging, walls, restore).
 * ResearchThread  — renders the conversation: each turn's question, cited answer, chart, cited bills,
 *                   and the paginated relevant-bills table on the latest turn. Owns its citation modal.
 * ResearchWall    — the sign-in / upgrade wall shown when the reader hits their access limit.
 */
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { CAP, useAuth } from '@/components/auth/AuthContext';
import { ApiError, askResearch, fetchMyResearchSessions, fetchResearchBills, fetchResearchSession } from '@/lib/api';
import type { BillSummary, ResearchAnswer, ResearchBillPage, ResearchChart, ResearchCitation } from '@/lib/types';
import { BillTable } from '@/components/bills/BillTable';
import { BillModal } from '@/components/ui/BillModal';
import { track } from '@/lib/analytics';
import { useChartTheme } from '@/lib/charts/theme';

// Local marker that an anonymous visitor has spent their one free question (server enforces the real
// per-IP/day limit; this just avoids a wasted round-trip and shows the wall immediately).
const FREE_ASK_KEY = 'atlas_free_ask_used';

/**
 * Whether an anonymous visitor has already spent their one free question — readable WITHOUT hosting the
 * ask state machine, so the homepage can show its "start free" pitch to someone who hit the limit over
 * on /ask. Mirrors the marker useResearch() writes; the server enforces the real per-IP/day limit.
 */
export function useFreeAskUsed(): boolean {
  const [used, setUsed] = useState(false);
  useEffect(() => {
    try { setUsed(localStorage.getItem(FREE_ASK_KEY) === '1'); } catch { /* ignore */ }
  }, []);
  return used;
}

export const RESEARCH_EXAMPLES = [
  'Do bills measure collection targets by weight or by value recovered?',
  'Which compliance dimensions are most common across bills?',
  'What design attributes do bills eco-modulate fees on?',
  'Which bills ban PFAS in packaging?',
];

// ---------------------------------------------------------------------------
// The ask state machine
// ---------------------------------------------------------------------------
export function useResearch() {
  const { user, hasCapability, getToken, loading: authLoading } = useAuth();
  const canAsk = hasCapability(CAP.ASK);
  const [wall, setWall] = useState<null | 'signin' | 'upgrade'>(null);
  const [freeAskUsed, setFreeAskUsed] = useState(false);
  const [turns, setTurns] = useState<{ q: string; answer: ResearchAnswer }[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [billPage, setBillPage] = useState<ResearchBillPage | null>(null);
  const [lastQuery, setLastQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [pageBusy, setPageBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The request never completed (the connection dropped, a browser/proxy cut the long request, the tab
  // was backgrounded) — distinct from an error the server actually answered with. The server finishes
  // and PERSISTS the turn regardless, so this state points the reader at their saved copy.
  const [dropped, setDropped] = useState(false);
  // The question of the last attempt, so a failed ask can be retried without retyping it.
  const [lastAsked, setLastAsked] = useState('');
  // Chasing the saved copy of an answer whose connection dropped (see recoverAnswer).
  const [recovering, setRecovering] = useState(false);
  // Generation token: a newer ask / new thread invalidates an in-flight recovery poll.
  const recoverGen = useRef(0);
  const [restoring, setRestoring] = useState(false);
  const [restored, setRestored] = useState(false);

  // Reopen a saved thread from My Library: ?session=<id> loads the owned conversation and threads any
  // follow-up onto it. Read from the URL directly (not useSearchParams) so the hosting client page
  // needs no Suspense boundary; runs once auth is ready.
  useEffect(() => {
    if (authLoading || typeof window === 'undefined') return;
    const sid = new URLSearchParams(window.location.search).get('session');
    if (!sid) return;
    let cancelled = false;
    setRestoring(true);
    setError(null);
    (async () => {
      try {
        const s = await fetchResearchSession(sid, await getToken());
        if (cancelled) return;
        setTurns(s.turns.map(t => ({
          q: t.question,
          answer: { answer: t.answer ?? '', citations: [] } as ResearchAnswer,
        })));
        setSessionId(s.session_id);
        setRestored(true);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not open that research thread.');
      } finally {
        if (!cancelled) setRestoring(false);
      }
    })();
    return () => { cancelled = true; };
    // Run once on mount after auth resolves; getToken is stable enough for a one-shot restore.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  // Anonymous visitors: remember once they've spent their free question so the wall shows immediately.
  useEffect(() => {
    if (!user && typeof window !== 'undefined') {
      try { setFreeAskUsed(localStorage.getItem(FREE_ASK_KEY) === '1'); } catch { /* ignore */ }
    }
  }, [user]);

  /**
   * The connection dropped, but the server keeps going and PERSISTS the finished turn — so the answer
   * exists, it just never reached this page. Poll the reader's own saved threads until it lands and show
   * it here, rather than making them go find it in My Library. Members only (an anonymous ask is
   * stateless — nothing was saved, so there is nothing to recover).
   *
   * `sid` is set on a follow-up (we already know the thread); on a first turn it's null and the new
   * session is matched by title, which `_persist_turn` stores as the question's first 200 chars. Newest
   * first, so re-asking a question you asked before still finds THIS one. A recovered turn carries no
   * citations (they aren't persisted per turn), so its [STATE BILL_NUMBER] markers read as plain text —
   * the same limitation as reopening a thread from My Library.
   */
  async function recoverAnswer(q: string, sid: string | null, priorTurns: number, windowMs = 150_000) {
    if (!user) return false;
    const gen = ++recoverGen.current;
    const title = q.slice(0, 200).trim();
    setRecovering(true);
    const deadline = performance.now() + windowMs;
    try {
      while (performance.now() < deadline) {
        await new Promise(r => setTimeout(r, 3000));
        if (recoverGen.current !== gen) return false;   // superseded by a retry or a new thread
        try {
          const token = await getToken();
          let targetId = sid;
          if (!targetId) {
            const list = await fetchMyResearchSessions(token);
            targetId = list.find(s => (s.title ?? '').trim() === title)?.session_id ?? null;
          }
          if (!targetId) continue;
          const s = await fetchResearchSession(targetId, token);
          if (s.turns.length <= priorTurns) continue;   // the turn hasn't been written yet
          if (recoverGen.current !== gen) return false;
          setTurns(s.turns.map(t => ({
            q: t.question,
            answer: { answer: t.answer ?? '', citations: [] } as ResearchAnswer,
          })));
          setSessionId(s.session_id);
          setDropped(false);
          track('atlas_query_recovered', { query_length: q.length });
          return true;
        } catch { /* transient — keep polling until the deadline, then leave the Library link */ }
      }
    } finally {
      if (recoverGen.current === gen) setRecovering(false);
    }
    return false;
  }

  /**
   * Pick a question back up after a reload. /ask keeps the question in the URL while it's in flight, so
   * a refresh mid-ask would otherwise fire a SECOND deep read — real money, for an answer the server is
   * already writing. Look for the saved copy first (short window: if it isn't there in ~20s the original
   * request probably never reached synthesis), and only ask fresh when there's nothing to pick up.
   */
  async function resume(q: string) {
    const found = await recoverAnswer(q, null, turns.length, 20_000);
    if (!found) await ask(q);
  }

  async function ask(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 3 || busy) return;
    // Wall the right people before spending a request.
    if (user && !canAsk) { setWall('upgrade'); return; }
    if (!user && freeAskUsed) { setWall('signin'); return; }
    recoverGen.current++;                       // a fresh ask supersedes any in-flight recovery poll
    setRecovering(false);
    setBusy(true); setError(null); setDropped(false); setWall(null); setLastAsked(trimmed);
    const t0 = performance.now();
    try {
      const token = await getToken();
      const a = await askResearch(trimmed, token, sessionId);
      // Core-value instrumentation: did the ask return something, and how fast. result_count is the
      // total relevant bills the retrieval found (0 = we couldn't answer from the corpus — its own
      // event so it's alertable). PII rule: length of the question, never its text.
      const latencyMs = Math.round(performance.now() - t0);
      const resultCount = a.bills?.total ?? a.citations?.length ?? 0;
      track('atlas_query_submitted', { query_length: trimmed.length, result_count: resultCount, latency_ms: latencyMs });
      if (resultCount === 0) {
        track('atlas_query_zero_results', { query_length: trimmed.length, latency_ms: latencyMs });
      }
      setTurns(prev => [...prev, { q: trimmed, answer: a }]);
      setSessionId(a.session_id ?? sessionId);
      setBillPage(a.bills ?? null);
      setLastQuery(a.retrieval_query ?? trimmed);
      if (!user && typeof window !== 'undefined') {
        try { localStorage.setItem(FREE_ASK_KEY, '1'); } catch { /* ignore */ }
        setFreeAskUsed(true);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setWall(e.detail === 'ask_upgrade_required' ? 'upgrade' : 'signin');
        if (!user) { try { localStorage.setItem(FREE_ASK_KEY, '1'); } catch { /* ignore */ } setFreeAskUsed(true); }
      } else if (e instanceof ApiError) {
        setError(e.message);
      } else {
        // fetch() rejects with a TypeError only when the request never completed — no status, no body.
        // A deep-read ask can run past a minute, and a browser/proxy network cap (~60s in Safari and
        // most corporate proxies) cuts it there. The answer isn't lost: the server keeps going and
        // saves the turn, so `dropped` sends the reader to My Library instead of showing nothing.
        setDropped(true);
        track('atlas_query_dropped', { query_length: trimmed.length, latency_ms: Math.round(performance.now() - t0) });
        void recoverAnswer(trimmed, sessionId, turns.length);
      }
    } finally {
      setBusy(false);
    }
  }

  function newThread() {
    recoverGen.current++; setRecovering(false);
    setTurns([]); setSessionId(null); setBillPage(null); setLastQuery('');
    setError(null); setDropped(false); setLastAsked(''); setRestored(false); setWall(null);
    // Drop ?session= so a fresh thread isn't tied to the reopened one (and a reload starts clean).
    if (typeof window !== 'undefined' && window.location.search.includes('session=')) {
      window.history.replaceState(null, '', window.location.pathname);
    }
  }

  async function goToPage(page: number) {
    if (!billPage || pageBusy) return;
    setPageBusy(true);
    try {
      const token = await getToken();
      setBillPage(await fetchResearchBills(lastQuery, page, billPage.page_size, token));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setPageBusy(false);
    }
  }

  return {
    authLoading, user, canAsk, freeAskUsed,
    turns, sessionId, billPage, pageBusy, busy, error, dropped, recovering, lastAsked,
    wall, setWall, restoring, restored,
    ask, resume, newThread, goToPage,
    retry: () => { if (lastAsked) ask(lastAsked); },
    hasAsked: turns.length > 0,
    // True whenever the reader is in an ask interaction (so a host can swap browse → answer view).
    // A failure counts: without it the surface unmounted the moment an ask errored, taking the error
    // message down with it — the reader just saw the page snap back to browsing with no explanation.
    active: turns.length > 0 || busy || restoring || recovering || wall !== null || error !== null || dropped,
  };
}

export type ResearchState = ReturnType<typeof useResearch>;

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/** The synthesis cites bills inline as `[STATE BILL_NUMBER]` (verbatim `ref`). */
function citationRef(c: ResearchCitation): string {
  return `${c.state ?? ''} ${c.bill_number ?? ''}`.trim();
}

/** Inline rendering: **bold** + clickable `[STATE BILL_NUMBER]` citations. */
function inline(line: string, cites: Map<string, ResearchCitation>, onCite: (c: ResearchCitation) => void) {
  return line.split(/(\*\*[^*]+\*\*|\[[^\][]+\])/g).map((p, j) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={j} className="text-text-primary font-semibold">{p.slice(2, -2)}</strong>;
    }
    if (p.startsWith('[') && p.endsWith(']')) {
      const c = cites.get(p.slice(1, -1));
      if (c?.bill) {
        return (
          <button
            key={j}
            type="button"
            onClick={() => onCite(c)}
            title={`Open ${citationRef(c)} details`}
            className="font-mono text-green-accent hover:underline focus:outline-none focus:underline"
          >
            {p}
          </button>
        );
      }
    }
    return <span key={j}>{p}</span>;
  });
}

function AnswerText({ text, cites, onCite }: {
  text: string;
  cites: Map<string, ResearchCitation>;
  onCite: (c: ResearchCitation) => void;
}) {
  return (
    <div className="space-y-2 text-body text-text-primary leading-relaxed">
      {text.split('\n').map(l => l.trimEnd()).filter(l => l.trim()).map((line, i) => {
        const t = line.trimStart();
        const hm = t.match(/^(#{1,6})\s+(.*)$/);
        if (hm) {
          const cls = hm[1].length <= 2
            ? 'font-serif text-lg text-text-primary mt-4 mb-1'
            : 'text-sm font-semibold uppercase tracking-wide text-text-secondary mt-3';
          return <div key={i} className={cls}>{inline(hm[2], cites, onCite)}</div>;
        }
        if (/^-{3,}$/.test(t)) return <hr key={i} className="border-border-default my-2" />;
        if (t.startsWith('- ') || t.startsWith('* ')) {
          return <p key={i} className="pl-4 -indent-4">{inline('• ' + t.slice(2), cites, onCite)}</p>;
        }
        return <p key={i}>{inline(line, cites, onCite)}</p>;
      })}
    </div>
  );
}

/**
 * A chart the answer chose to show. All numbers are computed server-side from SQL aggregates, so they're
 * exact; the model only picks WHICH aggregate is relevant and its `kind`. Renders one of four lightweight,
 * dependency-free forms by `kind` — bars (default / grouped), a trend line/area, or a part-to-whole donut
 * — colored from the shared chart primitive so identity/accent/status read the same as the Insights charts.
 */
function AnswerChart({ chart }: { chart: ResearchChart }) {
  const { title, kind, footnote } = chart;
  const body =
    kind === 'line' || kind === 'area' ? <TrendChart chart={chart} />
    : kind === 'donut' ? <DonutChart chart={chart} />
    : <BarsChart chart={chart} />;
  return (
    <div className="rounded-lg border border-border-default bg-bg-primary p-4 space-y-3">
      <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">{title}</div>
      {body}
      {footnote && <div className="text-[10px] text-text-muted leading-snug pt-1">{footnote}</div>}
    </div>
  );
}

// Default: horizontal bars, single-series or grouped (value inside value2, e.g. enacted ⊆ all-tracked).
function BarsChart({ chart }: { chart: ResearchChart }) {
  const { bars, kind, series } = chart;
  const grouped = kind === 'grouped';
  const max = Math.max(1, ...bars.map(b => (grouped ? (b.value2 ?? b.value) : b.value)));
  return (
    <>
      {grouped && series && series.length === 2 && (
        <div className="flex items-center gap-4 text-[11px] text-text-secondary">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-green-accent" />{series[0]}</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-green-accent/25" />{series[1]}</span>
        </div>
      )}
      <div className="space-y-2">
        {bars.map(b => (
          <div key={b.label} className="flex items-center gap-3">
            <div className="w-48 shrink-0 text-right">
              <div className="text-xs text-text-secondary truncate">{b.label}</div>
              {b.note && <div className="text-[10px] text-text-muted">{b.note}</div>}
            </div>
            <div className="relative flex-1 h-4 rounded bg-bg-tertiary overflow-hidden">
              {grouped && b.value2 != null && (
                <div className="absolute inset-y-0 left-0 rounded bg-green-accent/25" style={{ width: `${(b.value2 / max) * 100}%` }} />
              )}
              <div className="absolute inset-y-0 left-0 rounded bg-green-accent/80" style={{ width: `${(b.value / max) * 100}%` }} />
            </div>
            <div className="w-16 shrink-0 text-xs text-text-primary font-mono text-right">
              {b.value}{grouped && b.value2 != null && <span className="text-text-muted"> / {b.value2}</span>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// Trend over time: bars are (label=x, value=y), drawn as a connected line (area = filled underneath).
// A single accent line — one series, so the card title names it and no legend is needed. Falls back to
// bars if there are too few points to read as a trend.
function TrendChart({ chart }: { chart: ResearchChart }) {
  const colors = useChartTheme();
  const bars = chart.bars;
  if (bars.length < 2) return <BarsChart chart={{ ...chart, kind: 'bar' }} />;

  const W = 560, H = 190, PAD_L = 30, PAD_R = 12, PAD_T = 12, PAD_B = 22;
  const iw = W - PAD_L - PAD_R, ih = H - PAD_T - PAD_B;
  const n = bars.length;
  const maxV = Math.max(1, ...bars.map(b => b.value));
  const x = (i: number) => PAD_L + (i / (n - 1)) * iw;
  const y = (v: number) => PAD_T + ih - (v / maxV) * ih;
  const line = bars.map((b, i) => `${x(i).toFixed(1)},${y(b.value).toFixed(1)}`).join(' ');
  const areaPts = `${PAD_L},${(PAD_T + ih).toFixed(1)} ${line} ${x(n - 1).toFixed(1)},${(PAD_T + ih).toFixed(1)}`;
  const stroke = colors.accent;
  // Thin out x labels so they never collide: always the ends, then a sparse interior sample.
  const every = Math.max(1, Math.ceil(n / 7));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={chart.title} preserveAspectRatio="none">
      {[0, 0.5, 1].map(t => {
        const gy = PAD_T + ih - t * ih;
        return (
          <g key={t}>
            <line x1={PAD_L} y1={gy} x2={W - PAD_R} y2={gy} stroke={colors.border} strokeDasharray="3 3" />
            <text x={PAD_L - 5} y={gy + 3} textAnchor="end" fontSize="9" fill={colors.muted}>{Math.round(t * maxV)}</text>
          </g>
        );
      })}
      {chart.kind === 'area' && <polygon points={areaPts} fill={stroke} fillOpacity={0.12} />}
      <polyline points={line} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {bars.map((b, i) => (
        <circle key={i} cx={x(i)} cy={y(b.value)} r={2.5} fill={stroke}>
          <title>{b.label}: {b.value}</title>
        </circle>
      ))}
      {bars.map((b, i) =>
        (i === 0 || i === n - 1 || i % every === 0)
          ? <text key={`x${i}`} x={x(i)} y={H - 6} textAnchor="middle" fontSize="9" fill={colors.muted}>{b.label}</text>
          : null,
      )}
    </svg>
  );
}

// Part-to-whole: each bar is a slice. One ring + a direct-labeled legend (value + %), so identity is never
// carried by color alone. Caps at 7 slices + "Other" — never cycles the 8-slot categorical palette.
function DonutChart({ chart }: { chart: ResearchChart }) {
  const colors = useChartTheme();
  const sorted = [...chart.bars].sort((a, b) => b.value - a.value);
  const slices = sorted.length > 8
    ? [...sorted.slice(0, 7), { label: 'Other', value: sorted.slice(7).reduce((s, b) => s + b.value, 0) }]
    : sorted;
  const total = slices.reduce((s, b) => s + b.value, 0) || 1;

  const C = 72, R = 60, r = 38;
  const polar = (rad: number, ang: number) => `${(C + rad * Math.cos(ang)).toFixed(2)},${(C + rad * Math.sin(ang)).toFixed(2)}`;
  let a0 = -Math.PI / 2;
  const arcs = slices.map((s, i) => {
    const a1 = a0 + (s.value / total) * 2 * Math.PI;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const d = `M ${polar(R, a0)} A ${R} ${R} 0 ${large} 1 ${polar(R, a1)} L ${polar(r, a1)} A ${r} ${r} 0 ${large} 0 ${polar(r, a0)} Z`;
    const arc = { d, color: colors.categorical[i % colors.categorical.length], label: s.label, value: s.value, pct: Math.round((s.value / total) * 100) };
    a0 = a1;
    return arc;
  });

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <svg viewBox="0 0 144 144" width={132} height={132} className="shrink-0" role="img" aria-label={chart.title}>
        {arcs.map((s, i) => (
          <path key={i} d={s.d} fill={s.color} stroke="var(--bg-primary)" strokeWidth={1.5}>
            <title>{s.label}: {s.value} ({s.pct}%)</title>
          </path>
        ))}
        <text x={C} y={C - 1} textAnchor="middle" fontSize="20" fontWeight="700" fill="var(--text-primary)">{total}</text>
        <text x={C} y={C + 13} textAnchor="middle" fontSize="9" fill="var(--text-muted)">total</text>
      </svg>
      <ul className="space-y-1 text-xs flex-1 min-w-[150px]">
        {arcs.map((s, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm shrink-0" style={{ background: s.color }} />
            <span className="text-text-secondary truncate flex-1">{s.label}</span>
            <span className="text-text-primary font-mono">{s.value}</span>
            <span className="text-text-muted w-9 text-right tabular-nums">{s.pct}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The list of cited bills — the header/count now lives on the disclosure toggle that wraps this. */
function CitedBills({ citations, onOpen }: { citations: ResearchCitation[]; onOpen: (b: BillSummary) => void }) {
  return (
    <div className="space-y-2">
      <ul className="space-y-2">
        {citations.map((c, i) => {
          const body = (
            <>
              <div className="text-body text-text-primary">
                <span className="font-mono text-green-accent text-sm">{c.state} {c.bill_number}</span>
                {c.region && c.region !== c.state && <span className="text-text-muted text-xs ml-2">{c.region}</span>}
                {c.year && <span className="text-text-muted text-xs ml-2">{c.year}</span>}
              </div>
              {c.snippet && <p className="text-xs text-text-muted italic mt-0.5 leading-snug">…{c.snippet}…</p>}
            </>
          );
          return c.bill ? (
            <li key={c.bill_id}>
              <button
                type="button"
                onClick={() => {
                  // Did the answer's citation drive the reader to a bill? position = rank in the cited list.
                  track('atlas_citation_clicked', { bill_id: c.bill!.id, position: i + 1 });
                  onOpen(c.bill!);
                }}
                className="w-full text-left border-l-2 border-green-accent/40 pl-3 rounded-sm hover:bg-bg-secondary focus:outline-none focus:bg-bg-secondary transition-colors"
              >
                {body}
              </button>
            </li>
          ) : (
            <li key={c.bill_id} className="border-l-2 border-green-accent/40 pl-3">{body}</li>
          );
        })}
      </ul>
    </div>
  );
}

/** Human-readable note for which retrieval tier produced the relevant set. */
function strategyLabel(strategy: string): string {
  const [base, tags] = strategy.split('·');
  const where = tags ? ` · ${tags}` : '';
  if (base.startsWith('dimension:')) {
    return `Compliance dimension: ${base.slice('dimension:'.length).replace(/_/g, ' ')}${where}`;
  }
  if (base === 'jurisdiction') return `Jurisdiction${tags ? `: ${tags}` : ''}`;
  if (base === 'material') return `Product / material${tags ? `: ${tags}` : ''}`;
  if (base === 'product') return `Product${tags ? `: ${tags}` : ''}`;
  if (base === 'instrument') return `Instrument${tags ? `: ${tags}` : ''}`;
  if (base === 'all') return 'All bills';
  if (base === 'text_broad') return `Broadened text & title match${where}`;
  return `Text & title match${where}`;
}

function BillPager({ page, busy, onGo }: { page: ResearchBillPage; busy: boolean; onGo: (p: number) => void }) {
  const pageCount = Math.max(1, Math.ceil(page.total / page.page_size));
  if (pageCount <= 1) return null;
  const start = (page.page - 1) * page.page_size + 1;
  const end = start + page.items.length - 1;
  return (
    <div className="flex items-center justify-between gap-3 pt-1">
      <span className="text-xs text-text-muted">{start}–{end} of {page.total}</span>
      <div className="flex items-center gap-2">
        <button onClick={() => onGo(page.page - 1)} disabled={busy || page.page <= 1}
          className="rounded-full border border-border-default px-3 py-1 text-xs text-text-secondary hover:text-text-primary disabled:opacity-30">Prev</button>
        <span className="text-xs text-text-muted">Page {page.page} / {pageCount}</span>
        <button onClick={() => onGo(page.page + 1)} disabled={busy || page.page >= pageCount}
          className="rounded-full border border-border-default px-3 py-1 text-xs text-text-secondary hover:text-text-primary disabled:opacity-30">Next</button>
      </div>
    </div>
  );
}

/** The sign-in / upgrade wall — shown when the reader hits their ask limit. */
export function ResearchWall({ wall, onSignIn }: { wall: 'signin' | 'upgrade'; onSignIn: () => void }) {
  return (
    <div className="rounded-lg border border-green-accent/40 bg-green-dark/40 p-5 space-y-3">
      <h2 className="font-serif text-lg text-text-primary">
        {wall === 'signin' ? 'That was your free question' : 'Ask the Atlas is a member feature'}
      </h2>
      <p className="text-body text-text-secondary">
        {wall === 'signin'
          ? 'Create a free account and choose a membership to keep asking — Students pay what they wish with a verified .edu email.'
          : 'Your plan includes browsing every bill. Upgrade to a Student, Research, or Pro membership to ask the Atlas.'}
      </p>
      <div className="flex flex-wrap gap-2">
        {wall === 'signin' && (
          <button type="button" onClick={onSignIn}
            className="rounded-full bg-green-accent px-5 py-2 text-sm font-medium text-bg-primary hover:opacity-90">
            Sign in / sign up
          </button>
        )}
        <Link href="/pricing" className="rounded-full border border-border-default px-5 py-2 text-sm text-text-secondary hover:text-text-primary">
          See memberships
        </Link>
      </div>
    </div>
  );
}

/** A small uppercase-meta disclosure toggle, styled to match the "More filters" control on the home
 *  explorer — a label, an optional count, and a chevron that rotates when open. */
function DisclosureToggle({ open, onToggle, label, count }: {
  open: boolean; onToggle: () => void; label: string; count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex items-center gap-1.5 text-text-secondary text-xs font-semibold uppercase tracking-wide transition-colors hover:text-text-primary"
    >
      <span>{label}{count != null ? ` (${count})` : ''}</span>
      <span className={`text-meta transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
    </button>
  );
}

/** One question + its answer. The whole answer collapses from the question row (so a long thread reads
 *  on one page), and the cited-bills list sits behind its own disclosure (revealed on click). */
function ThreadTurn({ turn, index, total, isLast, billPage, pageBusy, goToPage, onOpenBill }: {
  turn: { q: string; answer: ResearchAnswer };
  index: number;
  total: number;
  isLast: boolean;
  billPage: ResearchBillPage | null;
  pageBusy: boolean;
  goToPage: (p: number) => void;
  onOpenBill: (b: BillSummary) => void;
}) {
  const [answerOpen, setAnswerOpen] = useState(true);
  const [citesOpen, setCitesOpen] = useState(false);
  const cites = new Map<string, ResearchCitation>();
  for (const c of turn.answer.citations) if (c.bill) cites.set(citationRef(c), c);

  return (
    <div className="space-y-5 border-t border-border-default pt-6">
      {/* The question row is the collapse toggle for the whole answer. */}
      <button
        type="button"
        onClick={() => setAnswerOpen(o => !o)}
        aria-expanded={answerOpen}
        className="flex w-full items-start gap-2 text-left font-serif text-lg text-text-primary group"
      >
        <span className="shrink-0 text-green-accent">{total > 1 ? `Q${index + 1}.` : 'Q.'}</span>
        <span className="flex-1">{turn.q}</span>
        <span className={`shrink-0 mt-1 text-sm text-text-muted transition-transform group-hover:text-text-secondary ${answerOpen ? 'rotate-180' : ''}`}>▾</span>
      </button>

      {answerOpen && (
        <>
          <AnswerText
            text={turn.answer.answer}
            cites={cites}
            onCite={c => {
              if (!c.bill) return;
              // Inline citation click — same signal as the cited-bills list; position = rank in citations.
              track('atlas_citation_clicked', { bill_id: c.bill.id, position: turn.answer.citations.indexOf(c) + 1 });
              onOpenBill(c.bill);
            }}
          />

          {turn.answer.chart && turn.answer.chart.bars.length > 0 && <AnswerChart chart={turn.answer.chart} />}

          {turn.answer.citations.length > 0 && (
            <div className="space-y-2">
              <DisclosureToggle
                open={citesOpen}
                onToggle={() => setCitesOpen(o => !o)}
                label="Cited bills"
                count={turn.answer.citations.length}
              />
              {citesOpen && <CitedBills citations={turn.answer.citations} onOpen={onOpenBill} />}
            </div>
          )}

          {isLast && billPage && billPage.total > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-text-secondary text-xs font-semibold uppercase tracking-wide">
                  Relevant bills ({billPage.total})
                </div>
                <span className="text-xs text-text-muted">{strategyLabel(billPage.strategy)}</span>
              </div>
              <div className={pageBusy ? 'opacity-50 transition-opacity' : 'transition-opacity'}>
                <BillTable bills={billPage.items} />
              </div>
              <BillPager page={billPage} busy={pageBusy} onGo={goToPage} />
            </div>
          )}

          {turn.answer.coverage_note && (
            <p className="text-xs text-text-muted border-t border-border-default pt-3">{turn.answer.coverage_note}</p>
          )}
        </>
      )}
    </div>
  );
}

/** The conversation: each turn's question, grounded answer, chart, cited bills, and — on the latest
 *  turn — the paginated relevant-bills table (the shared evidence). Owns its own citation modal. */
export function ResearchThread({ research }: { research: ResearchState }) {
  const { turns, billPage, pageBusy, busy, error, dropped, recovering, user, retry, goToPage } = research;
  const [modalBill, setModalBill] = useState<BillSummary | null>(null);

  return (
    <>
      {error && (
        <div className="space-y-2 rounded-lg border border-border-default bg-bg-secondary p-4">
          <p className="text-sm text-error">{error}</p>
          <button type="button" onClick={retry} className="text-sm text-green-accent hover:underline">
            Ask again
          </button>
        </div>
      )}

      {/* Picking a question back up after a reload (resume) — no drop happened, so no alarm. */}
      {recovering && !dropped && (
        <div className="space-y-3 border-t border-border-default pt-6">
          <p className="text-sm text-text-secondary">Picking up where you left off — fetching your answer…</p>
          <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
        </div>
      )}

      {/* The connection dropped mid-ask. The server finishes the answer and saves it either way, so the
          honest thing is to say that and point at the saved copy — not to blank the page. */}
      {dropped && (
        <div className="space-y-3 rounded-lg border border-border-default bg-bg-secondary p-4">
          <p className="text-sm text-text-primary">
            The connection dropped before the answer came back.
            {!user && ' A long question can take a minute; a steady connection sees it through.'}
            {user && (recovering
              ? ' It was still saved — fetching your copy now…'
              : ' It was still saved — visit your Library for asked questions and answers.')}
          </p>
          {recovering && <div className="h-16 w-full animate-pulse rounded-lg bg-bg-tertiary" />}
          <div className="flex flex-wrap items-center gap-4">
            {user && (
              <Link href="/library" className="text-sm text-green-accent hover:underline">
                Open My Library →
              </Link>
            )}
            <button type="button" onClick={retry} className="text-sm text-green-accent hover:underline">
              Ask again
            </button>
          </div>
        </div>
      )}

      {turns.map((t, ti) => (
        <ThreadTurn
          key={ti}
          turn={t}
          index={ti}
          total={turns.length}
          isLast={ti === turns.length - 1}
          billPage={billPage}
          pageBusy={pageBusy}
          goToPage={goToPage}
          onOpenBill={setModalBill}
        />
      ))}

      {busy && (
        <div className="space-y-3 border-t border-border-default pt-6">
          <p className="text-sm text-text-secondary">
            {turns.length > 0
              ? 'Following up on the thread — reading the most relevant bills and synthesizing a cited answer.'
              : 'Reading the full text of the most relevant bills and synthesizing a cited answer — this takes a moment.'}
          </p>
          <div className="h-24 w-full animate-pulse rounded-lg bg-bg-tertiary" />
        </div>
      )}

      <BillModal bill={modalBill} onClose={() => setModalBill(null)} />
    </>
  );
}

'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { BillSummary } from '@/lib/types';
import { BillModal } from '@/components/ui/BillModal';
import { formatInstrumentType, fixEncoding } from '@/lib/utils';
import { regionLabel } from '@/components/insights/RegionFilter';
import { track } from '@/lib/analytics';

/**
 * Homepage-B explorer: the whole (already-filtered) bill set drawn as one mark per bill, grouped by a
 * switchable axis — Year, Material, Region, or Instrument (ranked). Clicking a mark opens the shared
 * BillModal quick-look. Colors come from the canonical status tokens (light/dark handled by the token
 * layer). The dense mark grid is built imperatively into a ref for performance (a few thousand nodes);
 * React owns the controls and the modal. The upstream Explore bar still filters what's passed in via
 * `bills`; this adds a status filter behind "More filters".
 *
 * Data note: a bill can carry several materials, so in the Material view it appears under each — that
 * view's counts are bill × material coverage (called out inline), while the headline count is distinct
 * bills.
 */
type View = 'year' | 'material' | 'region' | 'instrument';
const VIEWS: { id: View; label: string }[] = [
  { id: 'year', label: 'Year' },
  { id: 'material', label: 'Material' },
  { id: 'region', label: 'Region' },
  { id: 'instrument', label: 'Instrument' },
];
const FOLD_YEAR = 2005;
type Bucket = 'enacted' | 'progress' | 'stalled';
const STATUS_META: { id: Bucket; label: string; varName: string }[] = [
  { id: 'enacted', label: 'Enacted', varName: '--status-enacted' },
  { id: 'progress', label: 'In progress', varName: '--status-introduced' },
  { id: 'stalled', label: 'Stalled', varName: '--status-dormant' },
];

function bucketOf(status: string | null): Bucket {
  if (status === 'enacted') return 'enacted';
  if (status === 'failed' || status === 'vetoed' || status === 'repealed') return 'stalled';
  return 'progress';
}
function titleizeMaterial(m: string): string {
  return m.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function yearOf(b: BillSummary): number | null {
  // status_date (year of most recent status) is the canonical axis; fall back to last_action_date so a
  // bill still places when status_date is missing (some foreign rows, older snapshots).
  const s = b.status_date ?? b.last_action_date;
  if (!s) return null;
  const y = Number(s.slice(0, 4));
  return Number.isFinite(y) ? y : null;
}

export function BillDotExplorer({ bills }: { bills: BillSummary[] }) {
  const [view, setView] = useState<View>('year');
  const [moreOpen, setMoreOpen] = useState(false);
  const [statusOn, setStatusOn] = useState<Record<Bucket, boolean>>({ enacted: true, progress: true, stalled: true });
  const [modalBill, setModalBill] = useState<BillSummary | null>(null);

  const boardRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  const byId = useMemo(() => new Map(bills.map((b) => [b.id, b])), [bills]);
  const displayBills = useMemo(
    () => bills.filter((b) => statusOn[bucketOf(b.status)]),
    [bills, statusOn],
  );
  const maxYear = useMemo(
    () => displayBills.reduce((m, b) => Math.max(m, yearOf(b) ?? -Infinity), -Infinity),
    [displayBills],
  );

  // Build the mark grid imperatively — thousands of nodes, so we skip React reconciliation for them.
  useEffect(() => {
    const el = boardRef.current;
    if (!el) return;
    el.classList.toggle('ranked', view !== 'year');

    const dotsHtml = (list: BillSummary[]) =>
      list
        .map((b, i) => {
          const title = fixEncoding(b.title) || 'Untitled';
          const label = `${b.bill_number ? b.bill_number + ': ' : ''}${title}`;
          return `<span class="bde-dot ${bucketOf(b.status)}" data-id="${b.id}" role="button" tabindex="0" aria-label="${esc(label)}" style="animation-delay:${Math.min(i, 60) * 10}ms"></span>`;
        })
        .join('');

    const rowHtml = (headHtml: string, list: BillSummary[]) =>
      `<div class="bde-row">${headHtml}<div class="bde-dots">${dotsHtml(list)}</div></div>`;

    let html = '';
    if (view === 'year') {
      const groups = new Map<number, BillSummary[]>();
      const pre: BillSummary[] = [];
      for (const b of displayBills) {
        const y = yearOf(b);
        if (y == null) continue;
        if (y < FOLD_YEAR) pre.push(b);
        else (groups.get(y) ?? groups.set(y, []).get(y)!).push(b);
      }
      const years = [...groups.keys()].sort((a, b) => b - a);
      for (const y of years) {
        const list = groups.get(y)!;
        const ytd = y === maxYear ? '<span class="bde-ytd">YTD</span>' : '';
        const head = `<div class="bde-head"><div class="bde-num">${y}</div><div class="bde-count"><b>${list.length}</b> bills${ytd}</div></div>`;
        html += rowHtml(head, list);
      }
      if (pre.length) {
        const head = `<div class="bde-head"><div class="bde-num" style="font-size:1.25rem">Pre-${FOLD_YEAR}</div><div class="bde-count"><b>${pre.length}</b> bills</div></div>`;
        html += rowHtml(head, pre);
      }
    } else {
      const map = new Map<string, BillSummary[]>();
      const push = (k: string, b: BillSummary) => (map.get(k) ?? map.set(k, []).get(k)!).push(b);
      for (const b of displayBills) {
        if (view === 'material') {
          const mats = (b.material_categories ?? []).filter(Boolean);
          if (mats.length) mats.forEach((m) => push(m, b));
          else push('—', b);
        } else if (view === 'region') push(b.region || '—', b);
        else push(b.instrument_type || 'other', b);
      }
      const entries = [...map.entries()].sort((a, b) => b[1].length - a[1].length);
      entries.forEach(([key, list], i) => {
        const name =
          key === '—' ? 'Unspecified'
          : view === 'region' ? regionLabel(key)
          : view === 'instrument' ? formatInstrumentType(key)
          : titleizeMaterial(key);
        const head = `<div class="bde-head bde-rankrow"><span class="bde-rank">${String(i + 1).padStart(2, '0')}</span><div><div class="bde-name">${esc(name)}</div><div class="bde-count"><b>${list.length}</b> bills</div></div></div>`;
        html += rowHtml(head, list);
      });
    }
    el.innerHTML = html || '<p class="text-text-muted text-sm py-6">No bills match these filters.</p>';
  }, [view, displayBills, maxYear]);

  // Delegated interaction on the imperative board.
  const openFromEvent = (target: EventTarget | null) => {
    const dot = (target as HTMLElement | null)?.closest?.('.bde-dot') as HTMLElement | null;
    if (!dot) return;
    const bill = byId.get(Number(dot.dataset.id));
    if (bill) { setModalBill(bill); track('home_explorer_bill_open', { view, bill_id: bill.id }); }
  };
  const showTip = (e: React.MouseEvent) => {
    const tip = tipRef.current;
    const dot = (e.target as HTMLElement).closest?.('.bde-dot') as HTMLElement | null;
    if (!tip) return;
    if (!dot) { tip.classList.remove('on'); return; }
    const bill = byId.get(Number(dot.dataset.id));
    if (!bill) return;
    tip.innerHTML = `<div class="n">${esc(bill.bill_number || bill.region)}</div><div class="t">${esc(fixEncoding(bill.title) || 'Untitled')}</div>`;
    tip.classList.add('on');
    const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 16, y = e.clientY + 16;
    if (x + w + pad > window.innerWidth) x = e.clientX - w - 16;
    if (y + h + pad > window.innerHeight) y = e.clientY - h - 16;
    tip.style.left = Math.max(pad, x) + 'px';
    tip.style.top = Math.max(pad, y) + 'px';
  };

  return (
    <section>
      {/* Controls: view switcher + More filters */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="inline-flex rounded-lg border border-border-default bg-bg-secondary p-0.5" role="group" aria-label="Group bills by">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => { setView(v.id); track('home_explorer_view', { view: v.id }); }}
              aria-pressed={view === v.id}
              className={`px-3.5 py-1.5 text-sm rounded-md transition-colors ${
                view === v.id ? 'bg-green-accent text-bg-primary font-medium' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setMoreOpen((o) => !o)}
          aria-expanded={moreOpen}
          className="text-sm text-text-secondary hover:text-text-primary inline-flex items-center gap-1"
        >
          More filters <span className={`transition-transform ${moreOpen ? 'rotate-180' : ''}`}>▾</span>
        </button>
        <span className="ml-auto text-sm text-text-muted tabular-nums"><b className="text-text-primary font-semibold">{displayBills.length.toLocaleString()}</b> bills</span>
      </div>

      {moreOpen && (
        <div className="mb-4 flex flex-wrap items-center gap-2 border border-border-default rounded-lg bg-bg-secondary p-3">
          <span className="text-xs uppercase tracking-wider text-text-muted mr-1">Status</span>
          {STATUS_META.map((s) => {
            const on = statusOn[s.id];
            return (
              <button
                key={s.id}
                onClick={() => setStatusOn((prev) => ({ ...prev, [s.id]: !prev[s.id] }))}
                aria-pressed={on}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${
                  on ? 'border-border-default bg-bg-primary text-text-primary' : 'border-border-default bg-transparent text-text-muted opacity-60 hover:opacity-100'
                }`}
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? `var(${s.varName})` : 'transparent', border: `1.5px solid var(${s.varName})` }} />
                {s.label}
              </button>
            );
          })}
        </div>
      )}

      <p className="mb-3 text-xs text-text-muted leading-relaxed">
        Each square is one bill — click it for the quick look and full record.{' '}
        {view === 'material'
          ? 'A bill can cover several materials, so it appears under each; these counts are bill × material coverage.'
          : 'Placed by the year of its most recent legislative action.'}
      </p>

      {/* Imperative mark grid */}
      <div
        ref={boardRef}
        className="bde-board"
        onClick={(e) => openFromEvent(e.target)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openFromEvent(e.target); } }}
        onMouseMove={showTip}
        onMouseLeave={() => tipRef.current?.classList.remove('on')}
      />
      <div ref={tipRef} className="bde-tip" role="tooltip" />

      <BillModal bill={modalBill} onClose={() => setModalBill(null)} />
    </section>
  );
}

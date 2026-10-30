'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import type { BillSummary } from '@/lib/types';
import { fixEncoding, formatDate, formatInstrumentType, isWeakening, billHref } from '@/lib/utils';
import { BillModal } from '@/components/ui/BillModal';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { WatchStar } from '@/components/watchlist/WatchStar';
import { track } from '@/lib/analytics';
import { useSelectedBill } from '@/hooks/useSelectedBill';
import { useBill } from '@/hooks/useBills';
import { jurisdictionCell, profileHrefForBill } from '@/lib/jurisdictions';

interface BillTableProps {
  bills: BillSummary[];
  maxRows?: number;
  /** When set, show this many rows per page with manual Prev/Next paging. */
  autoPageSize?: number;
  /**
   * Drive the open bill through the ?bill= URL param instead of local state, so the address bar
   * reflects the open bill (shareable link, Back closes it, refresh restores it) and inbound deep
   * links open through the same path. Opt-in — left off for embeds and surfaces that manage their
   * own bill modal. See useSelectedBill.
   */
  urlSync?: boolean;
  /** With autoPageSize: the page sizes offered in the table footer ("Rows per page"). The host owns the
   *  value (autoPageSize) and hears changes through onPageSizeChange. Omitted → no size control. */
  pageSizeOptions?: number[];
  onPageSizeChange?: (n: number) => void;
  /** Row hover/focus → the bill under the pointer (null on leave). Lets a host map outline the row's
   *  jurisdiction. */
  onRowHover?: (bill: BillSummary | null) => void;
}

/** "California · US" — the jurisdiction's full name with its parent tag for sub-national units. The
 *  name links to that jurisdiction's profile (the way down the rabbit hole from any row);
 *  stopPropagation keeps the row's own open-the-bill handler from firing too. */
function JurisdictionLabel({ bill, className = '' }: { bill: BillSummary; className?: string }) {
  const { name, parent } = jurisdictionCell(bill.region, bill.state);
  const href = profileHrefForBill(bill.region, bill.state);
  return (
    <span className={className}>
      {href ? (
        <Link
          href={href}
          onClick={e => { e.stopPropagation(); track('cta_click', { entry_source: 'bill_table_jurisdiction' }); }}
          onKeyDown={e => e.stopPropagation()}
          title={`Open the ${name} profile`}
          className="text-text-primary font-medium underline decoration-transparent decoration-1 underline-offset-4 transition-colors hover:decoration-text-primary"
        >
          {name}
        </Link>
      ) : (
        <span className="text-text-primary font-medium">{name}</span>
      )}
      {parent && <span className="text-text-muted text-meta"> · {parent}</span>}
    </span>
  );
}

export function BillTable({
  bills, maxRows, autoPageSize, urlSync = false, pageSizeOptions, onPageSizeChange, onRowHover,
}: BillTableProps) {
  const [localSelectedId, setLocalSelectedId] = useState<number | null>(null);
  const urlSel = useSelectedBill();
  const selectedId = urlSync ? urlSel.selectedId : localSelectedId;
  const [page, setPage] = useState(0);

  const pageCount = autoPageSize ? Math.max(1, Math.ceil(bills.length / autoPageSize)) : 1;

  // Reset to the first page whenever the filtered list changes.
  useEffect(() => { setPage(0); }, [bills.length]);

  const safePage = page % pageCount;
  const displayBills = autoPageSize
    ? bills.slice(safePage * autoPageSize, safePage * autoPageSize + autoPageSize)
    : maxRows ? bills.slice(0, maxRows) : bills;
  // Resolve the open bill: prefer the currently-loaded set, but when it isn't there (an inbound link
  // to a bill outside the active filter/region, or beyond the fetch cap — e.g. a non-US bill) fetch
  // it by id so the modal still opens. The fetch only fires in urlSync mode and only on a miss.
  const localBill = bills.find(b => b.id === selectedId) ?? null;
  const needFetch = urlSync && selectedId !== null && !localBill;
  const { data: fetchedBill } = useBill(needFetch ? selectedId : null);
  const selectedBill = localBill ?? (needFetch ? fetchedBill ?? null : null);

  function closeBill() {
    if (urlSync) urlSel.closeBill();
    else setLocalSelectedId(null);
  }

  // Mid-funnel engagement: which bills people actually open. State/type tell us what content pulls.
  function openBill(bill: BillSummary) {
    track('bill_open', {
      bill_id: bill.id,
      state: bill.state,
      instrument_type: bill.instrument_type,
    });
    if (urlSync) urlSel.openBill(bill.id);
    else setLocalSelectedId(bill.id);
  }

  function LitigationBadge({ bill }: { bill: BillSummary }) {
    if (bill.litigation_case_count === 0) return null;
    const risk = bill.max_preemption_risk ?? 0;
    const cls = risk >= 70
      ? 'bg-red-100 dark:bg-red-950/50 border-red-400 dark:border-red-700 text-red-700 dark:text-red-300'
      : risk >= 40
        ? 'bg-amber-100 dark:bg-amber-950/50 border-amber-400 dark:border-amber-700 text-amber-700 dark:text-amber-300'
        : 'bg-bg-primary border-border-default text-text-muted';
    const n = bill.litigation_case_count;
    return (
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-meta font-medium border whitespace-nowrap ${cls}`}
        title={`${n} court case${n === 1 ? '' : 's'}`}
      >
        <span aria-hidden>⚖</span> {n}
        <span className="sr-only">{n === 1 ? 'court case' : 'court cases'}</span>
      </span>
    );
  }

  return (
    <div className="space-y-3">
      {/* ── Desktop table (hidden below sm) ──
          64px rows with titles allowed two lines (Carbon's "tall" row, reserved for data expected to
          run to two lines). Type/Status are narrow; litigation is no longer a mostly-empty column —
          it's a badge beside the status, shown only when a case exists. */}
      <div className="hidden sm:block overflow-x-auto rounded-lg border border-border-default">
        <table className="w-full text-sm table-fixed min-w-[40rem]">
          {/* Three columns: where · what · how far along. Bill number rides under the jurisdiction and the
              last-action date under the status, so each row reads as two lines in three places. The
              instrument type stays a filter (and in the bill view) rather than a column. */}
          <colgroup>
            <col className="w-[10rem]" />
            <col />
            <col className="w-[9.5rem]" />
            <col className="w-10" />
          </colgroup>
          <thead>
            <tr className="bg-bg-secondary border-b border-border-default h-10">
              <th scope="col" className="field-label px-3 text-left whitespace-nowrap">Jurisdiction</th>
              <th scope="col" className="field-label px-3 text-left">Title</th>
              <th scope="col" className="field-label px-3 text-left">Status</th>
              <th scope="col" className="px-2"><span className="sr-only">Watch</span></th>
            </tr>
          </thead>
          <tbody onMouseLeave={() => onRowHover?.(null)}>
            {displayBills.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-text-muted">
                  No bills match the current filters.
                </td>
              </tr>
            )}
            {displayBills.map(bill => (
              <tr
                key={bill.id}
                onClick={() => openBill(bill)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openBill(bill);
                  }
                }}
                onMouseEnter={() => onRowHover?.(bill)}
                onFocus={() => onRowHover?.(bill)}
                tabIndex={0}
                role="button"
                aria-label={`Open ${bill.state} ${bill.bill_number ?? 'bill'} details`}
                className="list-row h-16 align-middle"
              >
                <td className="px-3 py-2">
                  <JurisdictionLabel bill={bill} className="block truncate" />
                  <span className="mt-0.5 block truncate font-mono text-xs text-text-muted">
                    {bill.bill_number ?? '—'}
                    {bill.last_action_date && (
                      <span className="text-text-muted/60 ml-1" title={`${bill.last_action_date} session`}>
                        &rsquo;{bill.last_action_date.slice(2, 4)}
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2">
                  {/* Real crawlable link to the bill's page. A plain left-click keeps the fast in-app
                      modal; ⌘/ctrl/shift/middle-click follows the URL into a new tab. stopPropagation
                      keeps the row's own openBill handler from double-firing. Materials ride in the
                      tooltip now that the title may use both lines. */}
                  <a
                    href={billHref(bill)}
                    onClick={e => {
                      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) { e.stopPropagation(); return; }
                      e.preventDefault();
                      e.stopPropagation();
                      openBill(bill);
                    }}
                    className="line-clamp-2 leading-snug text-text-primary hover:underline"
                    title={[
                      fixEncoding(bill.title),
                      bill.material_categories?.length ? bill.material_categories.map(c => c.replace(/_/g, ' ')).join(', ') : '',
                    ].filter(Boolean).join(' — ')}
                  >
                    {fixEncoding(bill.title) || 'Untitled'}
                  </a>
                </td>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <StatusBadge status={bill.status} weakening={isWeakening(bill)} />
                    <LitigationBadge bill={bill} />
                  </span>
                  {bill.last_action_date && (
                    <span className="mt-0.5 block text-xs text-text-muted whitespace-nowrap" title={`${formatInstrumentType(bill.instrument_type)} · last action`}>
                      {formatDate(bill.last_action_date)}
                    </span>
                  )}
                </td>
                <td className="px-2 py-2 text-center whitespace-nowrap">
                  <WatchStar billId={bill.id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Mobile card list (hidden at sm and above) ── */}
      <div className="sm:hidden space-y-2">
        {displayBills.length === 0 && (
          <div className="px-3 py-6 text-center text-text-muted text-sm">
            No bills match the current filters.
          </div>
        )}
        {displayBills.map(bill => (
          <div
            key={bill.id}
            onClick={() => openBill(bill)}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openBill(bill);
              }
            }}
            tabIndex={0}
            role="button"
            aria-label={`Open ${bill.state} ${bill.bill_number ?? 'bill'} details`}
            className="list-card p-3 space-y-1.5 active:bg-bg-tertiary"
          >
            {/* Row 1: jurisdiction / bill# / litigation */}
            <div className="flex items-center gap-2 flex-wrap">
              <JurisdictionLabel bill={bill} className="text-sm" />
              {bill.bill_number && (
                <span className="text-text-muted font-mono text-xs">
                  {bill.bill_number}
                  {bill.last_action_date && <span className="text-text-muted/60">&nbsp;&rsquo;{bill.last_action_date.slice(2, 4)}</span>}
                </span>
              )}
              <LitigationBadge bill={bill} />
              <span className="ml-auto"><WatchStar billId={bill.id} /></span>
            </div>
            {/* Row 2: title (2-line clamp) — real link to the bill page (see desktop cell note) */}
            <a
              href={billHref(bill)}
              onClick={e => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) { e.stopPropagation(); return; }
                e.preventDefault();
                e.stopPropagation();
                openBill(bill);
              }}
              className="text-text-primary text-sm line-clamp-2 hover:underline"
            >
              {fixEncoding(bill.title) || 'Untitled'}
            </a>
            {/* Row 3: materials */}
            {bill.material_categories && bill.material_categories.length > 0 && (
              <div className="text-text-muted text-xs">
                {bill.material_categories.slice(0, 3).map(c => c.replace(/_/g, ' ')).join(' · ')}
              </div>
            )}
            {/* Row 4: status + last action + expand indicator */}
            <div className="flex items-center justify-between text-xs">
              <StatusBadge status={bill.status} weakening={isWeakening(bill)} />
              <div className="flex items-center gap-3 text-text-muted">
                <span>{formatDate(bill.last_action_date)}</span>
                <span>›</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer: rows-per-page on the left (moved down from the toolbar — it's a property of this
          table, not of the filters), range + pager on the right. */}
      {autoPageSize && (pageCount > 1 || pageSizeOptions) ? (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs text-text-muted">
          <div className="flex items-center gap-4">
            {pageSizeOptions && onPageSizeChange && (
              <label className="flex items-center gap-1.5">
                Rows per page
                <select
                  value={autoPageSize}
                  onChange={e => onPageSizeChange(Number(e.target.value))}
                  className="rounded border border-border-default bg-bg-secondary px-1.5 py-0.5 text-xs text-text-primary focus:border-text-primary focus:outline-none"
                >
                  {pageSizeOptions.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
            )}
            <span className="tabular-nums">
              {bills.length === 0 ? 0 : (safePage * autoPageSize + 1).toLocaleString('en-US')}&ndash;{Math.min((safePage + 1) * autoPageSize, bills.length).toLocaleString('en-US')} of {bills.length.toLocaleString('en-US')}
            </span>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={safePage === 0}
                className="hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
                aria-label="Previous page"
              >
                &lsaquo; Prev
              </button>
              <span className="tabular-nums">Page {safePage + 1} / {pageCount.toLocaleString('en-US')}</span>
              <button
                onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))}
                disabled={safePage >= pageCount - 1}
                className="hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
                aria-label="Next page"
              >
                Next &rsaquo;
              </button>
            </div>
          )}
        </div>
      ) : bills.length > (maxRows ?? Infinity) ? (
        <div className="text-text-muted text-xs text-right">
          Showing {maxRows} of {bills.length.toLocaleString('en-US')} bills
        </div>
      ) : null}

      <BillModal bill={selectedBill} onClose={closeBill} />
    </div>
  );
}

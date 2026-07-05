'use client';
import { forwardRef } from 'react';
import Link from 'next/link';
import {
  daysUntil,
  formatLabelDate,
  formatMoney,
  type RegulationLabel,
} from '@/lib/label';
import { track } from '@/lib/analytics';
import { CliffGauge } from './CliffGauge';
import styles from './RegulationLabel.module.css';

const prettyMaterial = (s: string) => s.replace(/_/g, ' ');

/**
 * The FDA-style "Regulation Facts" panel. Renders either a product-mode label (aggregated
 * pathways per market) or a company-mode label (obligations per state + dollar stakes).
 * The ref targets the exportable node for html-to-image.
 */
export const RegulationLabelPanel = forwardRef<HTMLDivElement, { label: RegulationLabel }>(
  function RegulationLabelPanel({ label }, ref) {
    const t = label.totals;
    const soon = t.soonestDeadline;
    const anyUnsupported = label.jurisdictions.some(j => j.unsupported);
    const feeRange = label.finance
      ? (() => {
          const lo = formatMoney(label.finance.feeLowUsd);
          const hi = formatMoney(label.finance.feeHighUsd);
          if (!hi) return null;
          return lo && lo !== hi ? `${lo}–${hi}` : hi;
        })()
      : null;

    return (
      <div ref={ref} className={styles.label}>
        <p className={styles.brandTitle}>Regulation Facts</p>
        <div className={styles.serving}>
          <span>{label.mode === 'company' ? 'Company' : 'Product'}</span>
          <b>{label.subjectName}</b>
        </div>
        <div className={styles.serving}>
          <span>Markets on label</span>
          <b>{t.jurisdictions}</b>
        </div>

        <div className={styles.barThick} />
        <div className={styles.amountPer}>
          Amount per {label.mode === 'company' ? 'company' : 'product'}
        </div>
        <div className={styles.headline}>
          <span className="word" style={{ fontSize: 26, fontWeight: 900, letterSpacing: '-0.5px' }}>
            Obligations
          </span>
          <span style={{ fontSize: 34, fontWeight: 900 }}>{t.obligations}</span>
        </div>
        <div className={styles.pctHead}>% Compliance Load*</div>

        {label.jurisdictions.length === 0 || t.obligations === 0 ? (
          label.jurisdictions.every(j => !j.unsupported && !j.error) ? (
            <p className={styles.emptyNote}>
              No obligations found — regulation-free in the selected markets. Enjoy it while it
              lasts.
            </p>
          ) : null
        ) : null}

        {label.jurisdictions.map(j => {
          if (j.unsupported) {
            return (
              <div key={j.code} className={`${styles.jrow} ${styles.jrowZero}`}>
                <div className="top" style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 400, color: '#666' }}>
                  <span>{j.code}</span>
                  <span>coverage pending&dagger;</span>
                </div>
              </div>
            );
          }
          const pct = t.obligations ? Math.round((j.obligations / t.obligations) * 100) : 0;
          return (
            <div key={j.code} className={`${styles.jrow} ${j.obligations ? '' : styles.jrowZero}`}>
              <div className="top" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontWeight: j.obligations ? 700 : 400, color: j.obligations ? undefined : '#666' }}>
                <span>
                  {j.code}
                  {j.error ? ' ⚠' : ''}
                </span>
                <span>
                  {j.obligations} obligation{j.obligations === 1 ? '' : 's'} &middot; {pct}%
                </span>
              </div>
              {j.actions.map((a, i) => {
                const hot = a.deadline != null && daysUntil(a.deadline) <= 90;
                return (
                  <div key={i} className={styles.sub}>
                    <span className="what" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {[a.bill, a.summary].filter(Boolean).join(' — ')}
                      {a.entity ? ` · ${a.entity}` : ''}
                    </span>
                    <span className={hot ? styles.dueHot : undefined} style={{ whiteSpace: 'nowrap' }}>
                      {a.deadline ? formatLabelDate(a.deadline) : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          );
        })}

        <div className={styles.barMed} />

        {label.cliff && (
          <div className={styles.cliff}>
            <CliffGauge score={label.cliff.score} color={label.cliff.verdict.color} />
            <div>
              <div className={styles.verdictTitle} style={{ color: label.cliff.verdict.color }}>
                {label.cliff.verdict.title}
              </div>
              <div className={styles.verdictSub}>{label.cliff.verdict.description}</div>
            </div>
          </div>
        )}

        <div className={styles.statline}>
          <span>
            <b>Producer fees</b> apply
          </span>
          <b>
            {t.fees} law{t.fees === 1 ? '' : 's'}
          </b>
        </div>
        <div className={styles.statline}>
          <span>
            <b>Deadlines</b> within 90 days
          </span>
          <b>{t.deadlinesWithin90}</b>
        </div>
        {soon && (
          <div className={styles.statline}>
            <span>
              <b>Next hard deadline</b> {soon.code}
              {soon.bill ? ` · ${soon.bill}` : ''}
            </span>
            <b className={soon.daysAway <= 90 ? styles.dueHot : undefined}>
              {formatLabelDate(soon.date)} ({soon.daysAway}d)
            </b>
          </div>
        )}
        {label.finance?.maxPenaltyPerDayUsd != null && (
          <div className={styles.statline}>
            <span>
              <b>Max statutory penalty</b>
            </span>
            <b className={styles.dueHot}>{formatMoney(label.finance.maxPenaltyPerDayUsd)} / day</b>
          </div>
        )}
        {feeRange && (
          <div className={styles.statline}>
            <span>
              <b>Est. annual program fees</b>
              {label.finance?.anyFeeGrounded ? ' (grounded in statute)' : ''}
            </span>
            <b>{feeRange}</b>
          </div>
        )}
        {label.finance?.ecoModulationSwingUsd != null && label.finance.ecoModulationSwingUsd > 0 && (
          <div className={styles.statline}>
            <span>
              <b>Eco-modulation lever</b>
            </span>
            <b style={{ color: '#1a7f5a' }}>
              up to {formatMoney(label.finance.ecoModulationSwingUsd)} swing
            </b>
          </div>
        )}

        <div className={styles.barThick} />

        {label.contains.length > 0 && (
          <div className={styles.contains}>Contains: {label.contains.join(', ')}</div>
        )}
        <div className={styles.ingredients}>
          Ingredients: {label.materials.length ? label.materials.map(prettyMaterial).join(', ') : 'all materials'}
        </div>
        {label.entities.length > 0 && (
          <div className={styles.ingredients}>Administered by: {label.entities.join('; ')}</div>
        )}

        <div className={styles.footnote}>
          *% Compliance Load = this market&rsquo;s share of the total obligations.{' '}
          {anyUnsupported ? '†Regional compliance pathways are not yet available for this market. ' : ''}
          Live data, not legal advice. Data as of{' '}
          {new Date(label.generatedAt).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
          .
        </div>

        <div className={styles.brandline}>
          <span className={styles.logo}>
            Signal<span>Scout</span>
          </span>
          <Link
            href="/compliance"
            className={styles.cta}
            onClick={() => track('label_cta_compliance', { mode: label.mode })}
          >
            Get your full compliance plan &rarr;
          </Link>
        </div>
      </div>
    );
  },
);

'use client';
import styles from './RegulationLabel.module.css';

/**
 * The 0-100 Cliff Score dial from compliance-cliff, restyled for the printed-label aesthetic:
 * a conic-gradient ring filled to the score, verdict-colored. Pure CSS — survives PNG export.
 */
export function CliffGauge({ score, color }: { score: number; color: string }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className={styles.gauge}
      style={{ background: `conic-gradient(${color} ${pct}%, #e2ddd2 0)` }}
      role="img"
      aria-label={`Cliff score ${pct} out of 100`}
    >
      <div className={styles.gaugeInner}>
        <b style={{ color }}>{pct}</b>
        <small>cliff score</small>
      </div>
    </div>
  );
}

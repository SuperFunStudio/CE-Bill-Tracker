'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { GazetteHeader } from '@/components/ui/GazetteHeader';
import { RegulationLabelPanel } from '@/components/label/RegulationLabelPanel';
import { CompanySearch } from '@/components/label/CompanySearch';
import { ProductPicker, REGION_CODES } from '@/components/label/ProductPicker';
import {
  buildProductLabel,
  buildCompanyLabel,
  fetchObligations,
  MAX_MARKETS,
  type RegulationLabel,
} from '@/lib/label';
import { track } from '@/lib/analytics';
import { useAuth } from '@/components/auth/AuthContext';
import type { CompanySummary } from '@/lib/types';

// Admin-only for now: Regulation Facts is still being validated, so the route is gated to
// allowlisted admin accounts (the nav item is hidden for everyone else — see TopNav). The
// shareable-label / trial-funnel role is deferred until it graduates to the public nav.

type Mode = 'product' | 'company';

const DEFAULT_MATERIALS = ['glass', 'paper_packaging'];
const DEFAULT_MARKETS = ['CA', 'CO', 'OR', 'ME', 'TX', 'EU'];

/** Selection → URL hash, so a copied link reopens the exact same label (static-export friendly). */
function encodeHash(
  mode: Mode,
  sel: { productName: string; materials: string[]; markets: string[] },
  company: { id: string; name: string } | null,
): string {
  const p = new URLSearchParams();
  p.set('mode', mode);
  if (mode === 'company' && company) {
    p.set('c', company.id);
    if (company.name) p.set('cn', company.name);
  } else {
    if (sel.materials.length) p.set('m', sel.materials.join(','));
    if (sel.markets.length) p.set('mk', sel.markets.join(','));
    if (sel.productName) p.set('p', sel.productName);
  }
  return p.toString();
}

export default function LabelPage() {
  const { isAdmin, loading: authLoading } = useAuth();
  const [mode, setMode] = useState<Mode>('product');
  const [productName, setProductName] = useState('');
  const [materials, setMaterials] = useState<Set<string>>(new Set(DEFAULT_MATERIALS));
  const [markets, setMarkets] = useState<Set<string>>(new Set(DEFAULT_MARKETS));
  const [company, setCompany] = useState<{ id: string; name: string } | null>(null);

  const [label, setLabel] = useState<RegulationLabel | null>(null);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const labelRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 2400);
  }

  const generateProduct = useCallback(
    async (name: string, mats: string[], mkts: string[], writeHash = true) => {
      const states = mkts.filter(c => !REGION_CODES.has(c));
      const regions = mkts.filter(c => REGION_CODES.has(c));
      if (!states.length && !regions.length) {
        setError('Pick at least one market.');
        return;
      }
      setError('');
      setBusy(true);
      try {
        const built = await buildProductLabel({ productName: name, materials: mats, states, regions });
        setLabel(built);
        track('label_generate', {
          mode: 'product',
          materials: mats.length,
          markets: mkts.length,
          obligations: built.totals.obligations,
          cliff_score: built.cliff?.score ?? 0,
        });
        if (writeHash && typeof window !== 'undefined') {
          window.history.replaceState(
            null,
            '',
            `#${encodeHash('product', { productName: name, materials: mats, markets: mkts }, null)}`,
          );
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Label failed — try again.');
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const generateCompany = useCallback(async (c: { id: string; name: string }, writeHash = true) => {
    setError('');
    setBusy(true);
    try {
      const obligations = await fetchObligations(c.id);
      const built = buildCompanyLabel(obligations);
      setLabel(built);
      setCompany({ id: c.id, name: obligations.company_name || c.name });
      track('label_generate', {
        mode: 'company',
        obligations: built.totals.obligations,
        cliff_score: built.cliff?.score ?? 0,
      });
      if (writeHash && typeof window !== 'undefined') {
        window.history.replaceState(
          null,
          '',
          `#${encodeHash('company', { productName: '', materials: [], markets: [] }, { id: c.id, name: obligations.company_name || c.name })}`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load that company.');
    } finally {
      setBusy(false);
    }
  }, []);

  // Auto-generate the default label on fresh visits so the page opens on the artifact,
  // not a blank placeholder. Shared links (with a hash) regenerate their own label instead.
  // Gated on isAdmin so a non-admin visitor never triggers the API fan-out.
  useEffect(() => {
    if (!isAdmin || typeof window === 'undefined' || window.location.hash) return;
    void generateProduct('', DEFAULT_MATERIALS, DEFAULT_MARKETS, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  // Restore a shared link: parse the hash once on mount and regenerate the same label.
  useEffect(() => {
    if (!isAdmin || typeof window === 'undefined' || !window.location.hash) return;
    const p = new URLSearchParams(window.location.hash.slice(1));
    const m = p.get('mode');
    if (m === 'company' && p.get('c')) {
      setMode('company');
      void generateCompany({ id: p.get('c')!, name: p.get('cn') ?? '' }, false);
    } else if (m === 'product') {
      const mats = (p.get('m') ?? '').split(',').filter(Boolean);
      const mkts = (p.get('mk') ?? '').split(',').filter(Boolean);
      const name = p.get('p') ?? '';
      setProductName(name);
      if (mats.length) setMaterials(new Set(mats));
      if (mkts.length) setMarkets(new Set(mkts));
      if (mkts.length) void generateProduct(name, mats, mkts, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  function toggle(set: Set<string>, value: string): Set<string> {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  }

  async function handleDownload() {
    const node = labelRef.current;
    if (!node || !label || downloading) return;
    setDownloading(true);
    try {
      const { toPng } = await import('html-to-image');
      const dataUrl = await toPng(node, { pixelRatio: 2, backgroundColor: '#fffef9' });
      const a = document.createElement('a');
      const slug = label.subjectName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'label';
      a.download = `regulation-facts-${slug}.png`;
      a.href = dataUrl;
      a.click();
      track('label_download_png', { mode: label.mode });
      showToast('PNG downloaded ✓');
    } catch {
      showToast('PNG export failed — try a screenshot.');
    } finally {
      setDownloading(false);
    }
  }

  async function handleShare() {
    if (!label) return;
    const hash =
      label.mode === 'company' && company
        ? encodeHash('company', { productName: '', materials: [], markets: [] }, company)
        : encodeHash('product', { productName, materials: [...materials], markets: [...markets] }, null);
    const url = `${window.location.origin}${window.location.pathname}#${hash}`;
    try {
      await navigator.clipboard.writeText(url);
      showToast('Share link copied ✓');
    } catch {
      showToast(url);
    }
    track('label_share_link', { mode: label.mode });
  }

  const tabClass = (active: boolean) =>
    `px-4 py-2 text-sm font-medium rounded-t-lg border border-b-0 transition-colors ${
      active
        ? 'bg-bg-secondary text-text-primary border-border-default'
        : 'bg-transparent text-text-muted border-transparent hover:text-text-secondary'
    }`;

  // Admin-only route guard. While auth is resolving, show a neutral placeholder; a non-admin
  // (signed-out or otherwise) never sees the tool. This is a UI visibility gate — the underlying
  // data (public /compliance/pathways + /companies endpoints) isn't secret, it's just not ready
  // to surface as a product yet.
  if (authLoading || !isAdmin) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="mt-20 text-center text-text-muted text-sm italic">
          {authLoading ? 'Checking access…' : 'This page is not available.'}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <GazetteHeader
        title="Regulation Facts"
        subtitle="The nutrition label for compliance — pick a product or a company, get the shareable scorecard."
      />

      <div className="flex flex-wrap gap-8 items-start">
        {/* ------------------------------------------------ input panel */}
        <div className="flex-1 min-w-[320px] max-w-md">
          <div className="flex gap-1" role="tablist" aria-label="Label mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'product'}
              className={tabClass(mode === 'product')}
              onClick={() => setMode('product')}
            >
              By product
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'company'}
              className={tabClass(mode === 'company')}
              onClick={() => setMode('company')}
            >
              By company
            </button>
          </div>

          <div className="bg-bg-secondary border border-border-default rounded-b-lg rounded-tr-lg p-5 space-y-4">
            {mode === 'product' ? (
              <>
                <div>
                  <h3 className="text-xs uppercase tracking-wider text-text-muted font-semibold mb-2">
                    Product name <span className="normal-case font-normal">(optional)</span>
                  </h3>
                  <input
                    type="text"
                    value={productName}
                    onChange={e => setProductName(e.target.value)}
                    placeholder="e.g. 12oz Cold Brew — glass bottle"
                    className="w-full px-3 py-2.5 text-sm bg-bg-primary border border-border-default rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-green-accent/40 focus:border-green-accent"
                  />
                </div>
                <ProductPicker
                  materials={materials}
                  markets={markets}
                  onToggleMaterial={m => setMaterials(prev => toggle(prev, m))}
                  onToggleMarket={c => setMarkets(prev => toggle(prev, c))}
                  onAddState={c => setMarkets(prev => new Set(prev).add(c))}
                />
                <button
                  type="button"
                  disabled={busy || markets.size === 0 || markets.size > MAX_MARKETS}
                  onClick={() => void generateProduct(productName, [...materials], [...markets])}
                  className="w-full py-2.5 rounded-lg bg-text-primary text-bg-primary text-sm font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                >
                  {busy ? 'Reading the law…' : 'Generate label'}
                </button>
              </>
            ) : (
              <>
                <div>
                  <h3 className="text-xs uppercase tracking-wider text-text-muted font-semibold mb-2">
                    Company
                  </h3>
                  <CompanySearch
                    disabled={busy}
                    onPick={c => {
                      track('label_company_selected', { has_hq: Boolean(c.hq_state) });
                      void generateCompany({ id: c.id, name: c.name });
                    }}
                  />
                </div>
                <p className="text-xs text-text-muted leading-relaxed">
                  Search 400+ tracked producers. The label prefills from that company&rsquo;s
                  matched obligations — enacted laws, deadlines, and the dollar figures written
                  into the statutes — and scores how close to the compliance cliff it stands.
                </p>
                {busy && <p className="text-sm text-text-secondary">Reading the statutes…</p>}
              </>
            )}

            {error && <p className="text-sm text-urgency-high">{error}</p>}
          </div>

          {label && (
            <div className="flex gap-2 mt-4">
              <button
                type="button"
                disabled={downloading}
                onClick={() => void handleDownload()}
                className="flex-1 py-2 rounded-lg border border-text-primary text-text-primary text-sm font-semibold hover:bg-bg-secondary transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {downloading ? 'Exporting…' : '⬇ Download PNG'}
              </button>
              <button
                type="button"
                onClick={() => void handleShare()}
                className="flex-1 py-2 rounded-lg border border-border-default text-text-secondary text-sm font-semibold hover:bg-bg-secondary transition-colors"
              >
                🔗 Copy share link
              </button>
            </div>
          )}
          {toast && <p className="text-xs text-text-muted mt-2 text-center">{toast}</p>}
        </div>

        {/* ------------------------------------------------ the label */}
        <div className="flex-1 min-w-[320px] flex justify-center">
          {label ? (
            <RegulationLabelPanel ref={labelRef} label={label} />
          ) : (
            <div className="w-[440px] max-w-full border-2 border-dashed border-border-default rounded-lg p-10 text-center text-text-muted text-sm italic">
              Your Regulation Facts will render here.
              {mode === 'product' ? ' Hit "Generate label".' : ' Pick a company above.'}
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-text-muted max-w-3xl">
        Figures are drawn live from the SignalScout API — enacted statutes, published fee
        schedules, and classified compliance pathways. Penalties are the statutory maximum; fees
        are volume-apportioned estimates. Live data, not legal advice.
      </p>
    </div>
  );
}

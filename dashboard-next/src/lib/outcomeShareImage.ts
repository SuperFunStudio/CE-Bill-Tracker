/**
 * Renders a documented outcome as a 1200×630 social card — the "download the asset" half of sharing
 * a headline, alongside the link.
 *
 * It reuses the globe from our own OG image rather than a second illustration: the globe is cropped
 * out of /og-image.png (whose left half is baked-in marketing copy we don't want) and laid down at low
 * alpha, so the card reads as the same object as every other Atlas Circular preview, washed back far
 * enough to leave the figure legible. Everything else is drawn.
 *
 * Canvas, not a server renderer: the site is a static export with no image route, and the figure is
 * already on the client. Nothing here touches the network except the same-origin PNG, so the canvas
 * never taints and toBlob() stays available.
 */

const W = 1200;
const H = 630;

// The dark palette, hard-coded. A shared asset shouldn't change appearance based on the theme the
// sharer happened to be using — these are the dark-mode tokens from globals.css, which is what
// /og-image.png was composed against.
const BG = '#111827';
const ACCENT = '#f3bcc3';
const TEXT = '#f3f4f6';
const MUTED = '#8b95a1';

// The globe occupies roughly the right 60% of the OG image; the left is the wordmark and tagline.
const GLOBE_CROP = { x: 470, y: 0, w: 730, h: 630 };
const GLOBE_ALPHA = 0.3;

export interface OutcomeCardContent {
  /** The headline figure, e.g. "100 million containers". */
  metric: string;
  /** What the figure measures. */
  label: string;
  /** The relatable equivalence, when there is one. */
  comparison?: string | null;
  /** Jurisdiction + bill, e.g. "Tasmania · act-2022-005". */
  attribution?: string | null;
}

/** The site's own faces where the browser has them loaded, falling back to ubiquitous stand-ins. */
function families(): { serif: string; sans: string } {
  const root = typeof document !== 'undefined' ? getComputedStyle(document.documentElement) : null;
  const serifVar = root?.getPropertyValue('--font-serif')?.trim();
  const sansVar = root?.getPropertyValue('--font-sans')?.trim();
  return {
    serif: [serifVar, "'Playfair Display'", 'Georgia', 'serif'].filter(Boolean).join(', '),
    sans: [sansVar, 'system-ui', "'Segoe UI'", 'sans-serif'].filter(Boolean).join(', '),
  };
}

/** Greedy word wrap. Returns at most `maxLines` lines, ellipsizing the last one if it overflows. */
function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width <= maxWidth || !line) {
      line = next;
      continue;
    }
    lines.push(line);
    line = word;
    if (lines.length === maxLines) break;
  }
  if (lines.length < maxLines && line) lines.push(line);
  if (lines.length === maxLines) {
    // The last line may still be over, or there may be words we never reached — ellipsize either way.
    let last = lines[maxLines - 1];
    const consumed = lines.join(' ').split(/\s+/).length;
    const truncated = consumed < words.length || ctx.measureText(last).width > maxWidth;
    if (truncated) {
      while (last.length > 1 && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
      lines[maxLines - 1] = `${last.trimEnd()}…`;
    }
  }
  return lines;
}

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    // A missing/blocked backdrop is not a reason to fail the download — the card still works flat.
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** Draw the card and hand back the canvas. Exported for previewing; most callers want downloadOutcomeCard. */
export async function renderOutcomeCard(content: OutcomeCardContent): Promise<HTMLCanvasElement> {
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  // letterSpacing is a recent addition and isn't in every TS DOM lib yet.
  const ctx = canvas.getContext('2d')! as CanvasRenderingContext2D & { letterSpacing?: string };
  const { serif, sans } = families();

  // Webfonts are loaded lazily; without this the first card can render in the fallback face.
  try {
    await document.fonts?.ready;
  } catch {
    /* no Font Loading API — the fallbacks in families() cover it */
  }

  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, W, H);

  const globe = await loadImage('/og-image.png');
  if (globe) {
    // Bleed off the right edge and slightly past top and bottom, so it reads as a backdrop rather
    // than a pasted-in thumbnail.
    ctx.save();
    ctx.globalAlpha = GLOBE_ALPHA;
    const destW = 840;
    const destH = (GLOBE_CROP.h / GLOBE_CROP.w) * destW;
    ctx.drawImage(
      globe,
      GLOBE_CROP.x, GLOBE_CROP.y, GLOBE_CROP.w, GLOBE_CROP.h,
      W - destW + 130, (H - destH) / 2, destW, destH,
    );
    ctx.restore();

    // Scrim across the left two-thirds: the figure sits over the globe's limb otherwise.
    const scrim = ctx.createLinearGradient(0, 0, W, 0);
    scrim.addColorStop(0, 'rgba(17,24,39,0.97)');
    scrim.addColorStop(0.55, 'rgba(17,24,39,0.85)');
    scrim.addColorStop(1, 'rgba(17,24,39,0)');
    ctx.fillStyle = scrim;
    ctx.fillRect(0, 0, W, H);
  }

  const x = 72;
  const colWidth = 700;
  let y = 108;

  // Kicker.
  ctx.fillStyle = ACCENT;
  ctx.font = `600 22px ${sans}`;
  try {
    ctx.letterSpacing = '3px';
  } catch {
    /* letterSpacing is Chrome/Safari-only; the kicker just sits tighter elsewhere */
  }
  ctx.fillText('DOCUMENTED OUTCOME', x, y);
  try {
    ctx.letterSpacing = '0px';
  } catch {
    /* see above */
  }
  y += 62;

  // The figure.
  ctx.fillStyle = ACCENT;
  ctx.font = `700 84px ${serif}`;
  for (const line of wrap(ctx, content.metric, colWidth, 2)) {
    ctx.fillText(line, x, y);
    y += 92;
  }
  y += 10;

  // What it measures. Two lines, not three: the worst case (2-line figure + label + 2-line
  // equivalence) has to clear the footer at H-62, and a third line here is what pushes it under.
  ctx.fillStyle = TEXT;
  ctx.font = `400 32px ${sans}`;
  for (const line of wrap(ctx, content.label, colWidth, 2)) {
    ctx.fillText(line, x, y);
    y += 42;
  }

  // The equivalence.
  if (content.comparison) {
    y += 16;
    ctx.fillStyle = MUTED;
    ctx.font = `400 28px ${sans}`;
    for (const line of wrap(ctx, content.comparison, colWidth, 2)) {
      ctx.fillText(line, x, y);
      y += 38;
    }
  }

  // Footer: the law on the left, the wordmark on the right.
  ctx.fillStyle = MUTED;
  ctx.font = `400 24px ${sans}`;
  if (content.attribution) ctx.fillText(content.attribution, x, H - 62);

  ctx.fillStyle = TEXT;
  ctx.font = `700 28px ${serif}`;
  const wordmarkWidth = ctx.measureText('Atlas Circular').width; // measured in the face it's drawn in
  ctx.fillText('Atlas Circular', x, H - 24);
  ctx.fillStyle = MUTED;
  ctx.font = `400 22px ${sans}`;
  ctx.fillText('atlascircular.com', x + wordmarkWidth + 28, H - 24);

  return canvas;
}

/** Render the card and save it as a PNG. Resolves once the download has been handed to the browser. */
export async function downloadOutcomeCard(content: OutcomeCardContent, filename: string): Promise<void> {
  const canvas = await renderOutcomeCard(content);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('Could not encode the card.');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoked on the next frame: revoking synchronously races the download in Safari.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

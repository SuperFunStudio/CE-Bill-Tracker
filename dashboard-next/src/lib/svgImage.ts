// Rasterise on-screen SVG figures into a 1200×630 share card (the OG/LinkedIn size), client-side.
//
// An SVG drawn as an <img> can't see the page's CSS, so the theme tokens it uses (var(--text-primary)…)
// are resolved to their computed values before serialising. Web fonts don't load inside an SVG image
// either; the font stacks already end in system fallbacks (Georgia, Roboto/system-ui), so text still sets.

const W = 1200;
const H = 630;

function resolveVars(markup: string): string {
  const css = getComputedStyle(document.documentElement);
  return markup.replace(/var\((--[\w-]+)\)/g, (_, name: string) => css.getPropertyValue(name).trim().replace(/"/g, "'") || 'currentColor');
}

function loadSvg(svg: SVGSVGElement, w: number, h: number): Promise<HTMLImageElement> {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute('width', String(w));
  clone.setAttribute('height', String(h));
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.style.width = `${w}px`;
  clone.style.height = `${h}px`;
  const markup = resolveVars(new XMLSerializer().serializeToString(clone));
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml;charset=utf-8' }));
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = e => { URL.revokeObjectURL(url); reject(e); };
    img.src = url;
  });
}

/** Fit (w,h) of aspect `ar` inside a box, centred. */
function contain(ar: number, x: number, y: number, bw: number, bh: number) {
  const w = Math.min(bw, bh * ar), h = w / ar;
  return { x: x + (bw - w) / 2, y: y + (bh - h) / 2, w, h };
}

export interface CardPanel { svg: SVGSVGElement; caption?: string }

/** Title + headline over one or two figures, with the site URL as a footer. Resolves to a PNG blob. */
export async function renderShareCard(opts: { title: string; headline: string; panels: CardPanel[]; footer: string }): Promise<Blob> {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string, fb: string) => css.getPropertyValue(n).trim() || fb;
  const bg = v('--bg-primary', '#f8f9fa'), ink = v('--text-primary', '#1a1a2e'), muted = v('--text-muted', '#6b7280');
  const serif = 'Georgia, "Times New Roman", serif', sans = 'Roboto, system-ui, Arial, sans-serif';

  const scale = 2; // crisp on retina feeds
  const canvas = document.createElement('canvas');
  canvas.width = W * scale;
  canvas.height = H * scale;
  const ctx = canvas.getContext('2d')!;
  ctx.scale(scale, scale);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  ctx.fillStyle = muted;
  ctx.font = `700 13px ${sans}`;
  ctx.fillText('CIRCULAR ECONOMY POLICIES', 48, 52);
  ctx.fillStyle = ink;
  ctx.font = `700 34px ${serif}`;
  ctx.fillText(opts.title, 48, 92, W - 96);
  ctx.font = `400 19px ${sans}`;
  ctx.fillStyle = ink;
  ctx.fillText(opts.headline, 48, 124, W - 96);

  const top = 146, bottom = H - 50, gap = 24;
  const cw = (W - 96 - gap * (opts.panels.length - 1)) / opts.panels.length;
  for (let i = 0; i < opts.panels.length; i++) {
    const { svg, caption } = opts.panels[i];
    const vb = svg.viewBox.baseVal;
    const ar = vb && vb.width ? vb.width / vb.height : 1300 / 760;
    const capH = caption ? 26 : 0;
    const box = contain(ar, 48 + i * (cw + gap), top + capH, cw, bottom - top - capH);
    const img = await loadSvg(svg, Math.round(box.w * scale), Math.round(box.h * scale));
    ctx.drawImage(img, box.x, box.y, box.w, box.h);
    if (caption) {
      ctx.fillStyle = ink;
      ctx.font = `700 20px ${serif}`;
      ctx.textAlign = 'center';
      ctx.fillText(caption, 48 + i * (cw + gap) + cw / 2, top + 18, cw);
      ctx.textAlign = 'left';
    }
  }

  ctx.fillStyle = muted;
  ctx.font = `400 13px ${sans}`;
  ctx.fillText('Diagram after the Ellen MacArthur Foundation butterfly · counts are laws tracked by Atlas Circular', 48, H - 22);
  ctx.textAlign = 'right';
  ctx.fillStyle = ink;
  ctx.font = `700 15px ${sans}`;
  ctx.fillText(opts.footer, W - 48, H - 22);

  return new Promise((resolve, reject) => canvas.toBlob(b => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/png'));
}

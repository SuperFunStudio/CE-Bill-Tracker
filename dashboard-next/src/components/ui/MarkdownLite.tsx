// Minimal markdown renderer for the linked research answers (## / ### headers, "- " bullets, --- rules,
// **bold**, and [text](url) links). Deliberately small — the corpus answers only use this subset, and
// the citation markers have already been rewritten server-side into real [ref](/?bill=<id>) links.
import React from 'react';

/** Inline: **bold** and [text](url) links. Links open in a new tab (they point at the live bill modal). */
function inline(text: string): React.ReactNode[] {
  // Split keeping **bold** and [label](url) tokens as their own parts.
  return text
    .split(/(\*\*[^*]+\*\*|\[[^\][]+\]\([^)]+\))/g)
    .map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={i} className="font-semibold text-text-primary">
            {part.slice(2, -2)}
          </strong>
        );
      }
      const link = part.match(/^\[([^\][]+)\]\(([^)]+)\)$/);
      if (link) {
        return (
          <a
            key={i}
            href={link[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-sm text-green-accent hover:underline"
          >
            {link[1]}
          </a>
        );
      }
      return <span key={i}>{part}</span>;
    });
}

export function MarkdownLite({ text, className = '' }: { text: string; className?: string }) {
  const lines = text.split('\n').map(l => l.trimEnd());
  return (
    <div className={`space-y-2 text-body text-text-primary leading-relaxed ${className}`}>
      {lines.map((line, i) => {
        const t = line.trimStart();
        if (!t) return null;
        const hm = t.match(/^(#{1,6})\s+(.*)$/);
        if (hm) {
          const cls =
            hm[1].length <= 2
              ? 'font-serif text-lg text-text-primary mt-4 mb-1'
              : 'text-sm font-semibold uppercase tracking-wide text-text-secondary mt-3';
          return (
            <div key={i} className={cls}>
              {inline(hm[2])}
            </div>
          );
        }
        if (/^-{3,}$/.test(t)) return <hr key={i} className="border-border-default my-2" />;
        if (t.startsWith('- ') || t.startsWith('* ')) {
          return (
            <p key={i} className="pl-4 -indent-4">
              {inline('• ' + t.slice(2))}
            </p>
          );
        }
        return <p key={i}>{inline(line)}</p>;
      })}
    </div>
  );
}

'use client';

// EU map area. EU-central law (Regulations/Directives) applies EU-wide, so there is no per-member
// geography to shade yet — that lights up in Phase B when member-state national law (e.g. Spain's
// Royal Decree 1055/2022, Germany's VerpackG) is ingested. Until then this is an intentional
// "transposition tracking — coming soon" shell standing in for the 27-country choropleth. The real
// greyed choropleth (react-simple-maps + a Europe TopoJSON) replaces this body once the asset lands.

const MEMBER_STATES = [
  'Austria', 'Belgium', 'Bulgaria', 'Croatia', 'Cyprus', 'Czechia', 'Denmark', 'Estonia',
  'Finland', 'France', 'Germany', 'Greece', 'Hungary', 'Ireland', 'Italy', 'Latvia', 'Lithuania',
  'Luxembourg', 'Malta', 'Netherlands', 'Poland', 'Portugal', 'Romania', 'Slovakia', 'Slovenia',
  'Spain', 'Sweden',
];

export function EuMemberMap({ height = 380 }: { height?: number }) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border-default bg-bg-secondary/40 text-center px-6"
      style={{ minHeight: height }}
    >
      <div className="text-meta uppercase tracking-wider text-text-muted">European Union · 27 member states</div>
      <h3 className="mt-2 font-serif text-xl text-text-primary">Member-state transposition tracking</h3>
      <p className="mt-2 max-w-md text-sm text-text-secondary">
        The EU directives &amp; regulations below apply <span className="text-text-primary">across all members</span>.
        Country-by-country national law — the operative reuse quotas, fees and deadlines (e.g. Spain&apos;s
        Royal Decree 1055/2022) — is coming next.
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-1.5 max-w-xl">
        {MEMBER_STATES.map(s => (
          <span
            key={s}
            className="rounded-full border border-border-default px-2 py-0.5 text-meta text-text-muted"
          >
            {s}
          </span>
        ))}
      </div>
      <div className="mt-4 text-meta uppercase tracking-wider text-text-muted">National law — coming soon</div>
    </div>
  );
}

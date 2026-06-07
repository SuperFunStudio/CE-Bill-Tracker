/**
 * Big centered gazette masthead. When it scrolls away, the condensed "Battle of the Bills"
 * brand appears in the nav bar (mobile top bar) / persists in the sidebar (desktop).
 */
export function Masthead() {
  return (
    <header className="text-center pt-2 pb-5 border-b-2 border-text-primary/80">
      <div className="border-t border-b border-text-primary/30 py-3">
        <h1 className="font-serif uppercase text-text-primary leading-none tracking-[0.06em] text-[2rem] sm:text-5xl">
          Battle of the Bills
        </h1>
      </div>
      <p className="mt-3 text-text-secondary text-sm sm:text-base font-serif italic">
        Tracking circularity-aligned legislation across the USA
      </p>
    </header>
  );
}

export function DemoBanner() {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== 'true') return null;
  return (
    <div className="bg-blue-100 dark:bg-blue-900/40 border border-blue-400 dark:border-blue-700 rounded-lg p-3 mb-4 text-blue-800 dark:text-blue-200 text-sm">
      <strong>Demo Mode</strong> — Showing Oregon focus. Data reflects OR SB 582 and NAW trial scenario.
    </div>
  );
}

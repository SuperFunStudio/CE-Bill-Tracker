import { STATE_NAMES } from '@/lib/utils';
import { StateProfile } from '@/components/states/StateProfile';

// Static export: pre-render one page per state (lowercase slug, e.g. /states/nm/).
export function generateStaticParams() {
  return Object.keys(STATE_NAMES).map(abbr => ({ abbr: abbr.toLowerCase() }));
}

export default function StateProfilePage({ params }: { params: { abbr: string } }) {
  return <StateProfile abbr={params.abbr.toUpperCase()} />;
}

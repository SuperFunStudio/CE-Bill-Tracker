import { allJurisdictionParams } from '@/lib/jurisdictions';
import { JurisdictionProfile } from '@/components/jurisdictions/JurisdictionProfile';

// Static export: pre-render one page per jurisdiction leaf (lowercase slugs, e.g. /jurisdictions/us/ca/,
// /jurisdictions/eu/eu/, /jurisdictions/jp/jp/). See allJurisdictionParams for the full set.
export function generateStaticParams() {
  return allJurisdictionParams();
}

export default function JurisdictionPage({ params }: { params: { region: string; code: string } }) {
  return <JurisdictionProfile region={params.region.toUpperCase()} code={params.code.toUpperCase()} />;
}

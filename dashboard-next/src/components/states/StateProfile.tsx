import { JurisdictionProfile } from '@/components/jurisdictions/JurisdictionProfile';

/**
 * US-state profile — now a thin alias over the region-aware {@link JurisdictionProfile}. Kept so the
 * back-compat route /states/[abbr] (and its inbound links) keep resolving to the US profile; the
 * canonical URL is /jurisdictions/us/[abbr].
 */
export function StateProfile({ abbr }: { abbr: string }) {
  return <JurisdictionProfile region="US" code={abbr} />;
}

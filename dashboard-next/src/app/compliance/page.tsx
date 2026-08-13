import type { Metadata } from 'next';
import CompliancePage from './CompliancePage';

// Server wrapper — see the note in methodology/page.tsx.
export const metadata: Metadata = {
  title: 'Compliance deadlines — what is due, and when | Atlas Circular',
  description:
    'The obligation dates extracted from enacted circular-economy law: producer registration, ' +
    'reporting, fee and program deadlines by jurisdiction and material, so a date lands on your ' +
    'calendar before it lands on you.',
  alternates: { canonical: '/compliance/' },
  openGraph: {
    title: 'Compliance deadlines — what is due, and when',
    description:
      'Registration, reporting and fee deadlines extracted from enacted EPR law, by jurisdiction.',
    url: '/compliance/',
  },
};

export default function Page() {
  return <CompliancePage />;
}

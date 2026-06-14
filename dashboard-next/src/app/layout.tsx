import type { Metadata } from 'next';
import { Inter, Spectral } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import { Providers } from '@/components/layout/Providers';
import { AppShell } from '@/components/layout/AppShell';
import { RouteAnalytics } from '@/components/layout/RouteAnalytics';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans', display: 'swap' });
const spectral = Spectral({
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
});

const SITE_URL = 'https://ce-bill-tracker.web.app';
const TITLE = 'Battle of the Bills — Circularity Legislation Tracker (Beta)';
const DESCRIPTION =
  'A real-time tracker for circularity-aligned legislation across all 50 US states.';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    type: 'website',
    url: SITE_URL,
    siteName: 'Battle of the Bills',
    title: TITLE,
    description: DESCRIPTION,
    images: [
      {
        url: '/og-image.png',
        width: 1200,
        height: 630,
        alt: 'Battle of the Bills — Circularity Legislation Tracker',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
    images: ['/og-image.png'],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${spectral.variable}`}>
      <body className="bg-bg-primary text-text-primary antialiased">
        <Providers>
          <AppShell>{children}</AppShell>
          <RouteAnalytics />
        </Providers>
        <Script
          src="https://www.googletagmanager.com/gtag/js?id=G-S858LD2MMN"
          strategy="afterInteractive"
        />
        <Script id="gtag-init" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            // send_page_view:false — RouteAnalytics owns page_view so SPA route changes are tracked
            // and the initial load isn't double-counted.
            gtag('config', 'G-S858LD2MMN', { send_page_view: false });
          `}
        </Script>
      </body>
    </html>
  );
}

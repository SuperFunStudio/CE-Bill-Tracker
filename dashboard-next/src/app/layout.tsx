import type { Metadata, Viewport } from 'next';
import { Playfair_Display, Roboto, Roboto_Mono } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import { Providers } from '@/components/layout/Providers';
import { AppShell } from '@/components/layout/AppShell';
import { RouteAnalytics } from '@/components/layout/RouteAnalytics';
import { SITE_NAME, SITE_TAGLINE } from '@/lib/brand';

// Atlas Circular brand type: Playfair Display is the display/masthead face (`--font-serif` — the token
// name is kept so the many existing masthead call sites don't have to change), Roboto is the body/UI
// face (`--font-sans`), Roboto Mono for labels/mono. Playfair falls back to Georgia (mirrors the email
// gazette face) and Roboto to Arial, so web and email read as one system.
const roboto = Roboto({ subsets: ['latin'], weight: ['400', '500', '700'], variable: '--font-sans', display: 'swap' });
const playfair = Playfair_Display({ subsets: ['latin'], weight: ['500', '600', '700', '800'], variable: '--font-serif', display: 'swap' });
const robotoMono = Roboto_Mono({ subsets: ['latin'], weight: ['400', '500', '700'], variable: '--font-mono', display: 'swap' });

const SITE_URL = 'https://www.atlascircular.com';
const TITLE = 'Atlas Circular — Circular Economy Legislation Tracker';
// The brand tagline is metadata + footer copy now (it was set too small to read under the nav
// wordmark), so it leads the description that search and share cards show.
const DESCRIPTION =
  `${SITE_TAGLINE} — track sustainability and circular-economy law across the globe: bills, deadlines, and analysis, by jurisdiction.`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  applicationName: SITE_NAME,
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    type: 'website',
    url: SITE_URL,
    siteName: 'Atlas Circular',
    title: TITLE,
    description: DESCRIPTION,
    // Share card: dark globe (US + Western Europe lit) + wordmark + coverage legend. Regenerate with
    // scripts/gen-og-globe.mjs then scripts/render-og-preview.mjs. ?v cache-busts social scrapers.
    images: [
      {
        url: '/og-image.png?v=3',
        width: 1200,
        height: 630,
        alt: 'Atlas Circular — a circular economy legislation tracker',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
    images: ['/og-image.png?v=3'],
  },
};

// theme-color renders <meta name="theme-color"> so the mobile browser chrome (status bar / URL bar)
// matches the app surface instead of defaulting to white. Starts at the light surface; the pre-paint
// script below and the theme toggle rewrite it to the dark surface when dark mode is active.
// color-scheme tells the UA to render native controls + scrollbars for both themes.
export const viewport: Viewport = {
  themeColor: '#ffffff',
  colorScheme: 'light dark',
};

// Sitewide structured data. Bill pages already emit schema.org `Legislation`; this is the publisher
// and search-action layer that identifies WHO stands behind those records — the thing a search engine
// or an assistant uses to decide whether a legislative claim is attributable. Rendered as a literal
// script tag in the server layout so it's in the HTML for clients that never run JavaScript, which is
// most crawlers and every AI crawler worth reaching.
const ORG_JSONLD = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: SITE_URL,
      slogan: SITE_TAGLINE,
      description: DESCRIPTION,
      logo: `${SITE_URL}/og-image.png`,
    },
    {
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      description: DESCRIPTION,
      publisher: { '@id': `${SITE_URL}/#organization` },
      inLanguage: 'en',
      // Declares that the corpus is searchable, and how — so an assistant can construct a query URL
      // instead of guessing or scraping the homepage.
      potentialAction: {
        '@type': 'SearchAction',
        target: {
          '@type': 'EntryPoint',
          urlTemplate: `${SITE_URL}/?q={search_term_string}`,
        },
        'query-input': 'required name=search_term_string',
      },
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${roboto.variable} ${playfair.variable} ${robotoMono.variable}`}>
      <body className="bg-bg-primary text-text-primary antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(ORG_JSONLD) }}
        />
        {/* Anti-FOUC: apply the saved (or OS-preferred) theme synchronously, BEFORE first paint, so a
            dark-mode load never flashes the light surface. Runs during HTML parse, ahead of the app.
            Mirrors ThemeContext's resolution so there's no post-hydration correction. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(!t){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}if(t==='dark'){document.documentElement.classList.add('dark');}var m=document.querySelector('meta[name="theme-color"]');if(m){m.setAttribute('content',t==='dark'?'#111827':'#ffffff');}}catch(e){}})();`,
          }}
        />
        {/* gtag SHIM — must run during HTML parse, before React hydrates. `window.gtag` only queues
            into dataLayer; the remote gtag/js script below drains that queue when it finishes loading,
            so nothing fired before load is lost.

            This used to be an afterInteractive <Script>, which raced RouteAnalytics: its mount effect
            runs at hydration, and lib/analytics track() silently no-ops when window.gtag is undefined.
            The initial page_view lost that race on most loads — GA recorded 419 session_start users
            against only 104 page_view users, and 74% of sessions had landingPage "(not set)". Defining
            the shim synchronously is what makes the first page_view of a session reliable. */}
        <Script id="gtag-shim" strategy="beforeInteractive">
          {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('js',new Date());gtag('config','G-S858LD2MMN',{send_page_view:false});`}
        </Script>
        <Providers>
          <AppShell>{children}</AppShell>
          <RouteAnalytics />
        </Providers>
        {/* send_page_view:false is set in the shim above — RouteAnalytics owns page_view so SPA route
            changes are tracked and the initial load isn't double-counted. */}
        <Script
          src="https://www.googletagmanager.com/gtag/js?id=G-S858LD2MMN"
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}

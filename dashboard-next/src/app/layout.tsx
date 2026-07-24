import type { Metadata, Viewport } from 'next';
import { Playfair_Display, Roboto, Roboto_Mono } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import { Providers } from '@/components/layout/Providers';
import { AppShell } from '@/components/layout/AppShell';
import { RouteAnalytics } from '@/components/layout/RouteAnalytics';

// Atlas Circular brand type: Playfair Display is the display/masthead face (`--font-serif` — the token
// name is kept so the many existing masthead call sites don't have to change), Roboto is the body/UI
// face (`--font-sans`), Roboto Mono for labels/mono. Playfair falls back to Georgia (mirrors the email
// gazette face) and Roboto to Arial, so web and email read as one system.
const roboto = Roboto({ subsets: ['latin'], weight: ['400', '500', '700'], variable: '--font-sans', display: 'swap' });
const playfair = Playfair_Display({ subsets: ['latin'], weight: ['500', '600', '700', '800'], variable: '--font-serif', display: 'swap' });
const robotoMono = Roboto_Mono({ subsets: ['latin'], weight: ['400', '500', '700'], variable: '--font-mono', display: 'swap' });

const SITE_URL = 'https://www.atlascircular.com';
const TITLE = 'Atlas Circular — A Circular-Economy Law Atlas';
const DESCRIPTION =
  'Track sustainability and circular-economy law across the globe — bills, deadlines, and analysis, by jurisdiction.';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    type: 'website',
    url: SITE_URL,
    siteName: 'Atlas Circular',
    title: TITLE,
    description: DESCRIPTION,
    images: [
      {
        url: '/og-image.png',
        width: 1200,
        height: 630,
        alt: 'Atlas Circular — A Circular-Economy Law Atlas',
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

// theme-color renders <meta name="theme-color"> so the mobile browser chrome (status bar / URL bar)
// matches the app surface instead of defaulting to white. Starts at the light surface; the pre-paint
// script below and the theme toggle rewrite it to the dark surface when dark mode is active.
// color-scheme tells the UA to render native controls + scrollbars for both themes.
export const viewport: Viewport = {
  themeColor: '#ffffff',
  colorScheme: 'light dark',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${roboto.variable} ${playfair.variable} ${robotoMono.variable}`}>
      <body className="bg-bg-primary text-text-primary antialiased">
        {/* Anti-FOUC: apply the saved (or OS-preferred) theme synchronously, BEFORE first paint, so a
            dark-mode load never flashes the light surface. Runs during HTML parse, ahead of the app.
            Mirrors ThemeContext's resolution so there's no post-hydration correction. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(!t){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}if(t==='dark'){document.documentElement.classList.add('dark');}var m=document.querySelector('meta[name="theme-color"]');if(m){m.setAttribute('content',t==='dark'?'#111827':'#ffffff');}}catch(e){}})();`,
          }}
        />
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

import type { Metadata } from 'next';
import { Inter, Spectral } from 'next/font/google';
import './globals.css';
import { Providers } from '@/components/layout/Providers';
import { TopNav } from '@/components/layout/TopNav';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans', display: 'swap' });
const spectral = Spectral({
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Battle of the Bills — Circularity Legislation Tracker (Beta)',
  description: 'A real-time tracker for circularity-aligned legislation across all 50 US states.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${spectral.variable}`}>
      <body className="bg-bg-primary text-text-primary antialiased">
        <Providers>
          <div className="flex flex-col h-screen overflow-hidden">
            <TopNav />
            <main className="flex-1 overflow-auto">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}

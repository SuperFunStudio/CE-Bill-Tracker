import type { Metadata } from 'next';
import './globals.css';
import { Providers } from '@/components/layout/Providers';
import { Sidebar } from '@/components/layout/Sidebar';

export const metadata: Metadata = {
  title: 'SignalScout — EPR Compliance Intelligence',
  description: 'Monitor US state-level EPR legislation, compliance deadlines, and company exposure.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-bg-primary text-text-primary antialiased">
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 overflow-auto pt-12 md:pt-0">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}

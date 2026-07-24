/** @type {import('next').NextConfig} */

// The production build is a STATIC EXPORT (output: 'export'), which cannot proxy/rewrite. In local
// `next dev` we drop the export and add a same-origin proxy so the browser talks to localhost instead
// of the prod Cloud Run API cross-origin (that API sends no CORS headers for localhost, so direct
// fetches load but are blocked from being read → an empty board). Set NEXT_PUBLIC_API_BASE_URL to
// `http://localhost:<port>/proxy-api` in .env.local to route through it. PROD IS UNAFFECTED.
const isDev = process.env.NODE_ENV === 'development';
const DEV_PROXY_TARGET = 'https://signalscout-api-36712717703.us-central1.run.app';

const nextConfig = {
  ...(isDev ? {} : { output: 'export' }),
  trailingSlash: true,
  images: { unoptimized: true },
  ...(isDev && {
    async rewrites() {
      return [{ source: '/proxy-api/:path*', destination: `${DEV_PROXY_TARGET}/:path*` }];
    },
  }),
};

export default nextConfig;

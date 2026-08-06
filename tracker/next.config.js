/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Cache static assets aggressively; ISR handles freshness of dynamic content
  headers: async () => [
    {
      source: "/data/:path*",
      headers: [
        { key: "Cache-Control", value: "public, max-age=300, s-maxage=3600" },
      ],
    },
  ],
};

module.exports = nextConfig;

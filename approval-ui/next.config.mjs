/** @type {import('next').NextConfig} */
const nextConfig = {
  // The API server (python -m roxi serve) runs on 8080.
  // In development the Next.js app proxies /api/* to it.
  // In production set ROXI_API_URL to your deployed API server URL.
  async rewrites() {
    const apiBase = process.env.ROXI_API_URL || "http://localhost:8080";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

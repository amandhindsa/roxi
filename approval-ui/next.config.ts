import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The API server (python -m roxi serve) runs on 8080.
  // In development the Next.js app proxies /api/leads/* to it.
  // In production with Supabase, the API routes talk to Supabase directly.
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

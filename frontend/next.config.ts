import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// Static export only: no SSR, server actions or API routes (build_spec.md §3).
const base: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // The HTTP-mode build (npm run build:http) exports to out-http/ so it never overwrites the preview build.
  ...(process.env.NEXT_PUBLIC_WORKWEAVE_MODE === "http" ? { distDir: "out-http" } : {}),
};

/**
 * `next dev` only: proxy /api/* to the local WorkWeave API so the page stays same-origin with its
 * HttpOnly session cookie (Firebase Hosting rewrites do the same in the cloud). Builds remain pure
 * static exports; rewrites aren't part of the exported site.
 */
export default function config(phase: string): NextConfig {
  if (phase !== PHASE_DEVELOPMENT_SERVER) return base;
  const api = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
  // Dev uses the default .next directory, and rewrites need the non-export dev server.
  return {
    trailingSlash: base.trailingSlash,
    images: base.images,
    reactStrictMode: base.reactStrictMode,
    // Without this, trailingSlash would redirect /api/x to /api/x/ before the proxy runs.
    skipTrailingSlashRedirect: true,
    // Project AI instructions live in src/CLAUDE.md; don't let `next dev` generate AGENTS.md/CLAUDE.md here.
    agentRules: false,
    rewrites: async () => [{ source: "/api/:path*", destination: `${api}/api/:path*` }],
  };
}

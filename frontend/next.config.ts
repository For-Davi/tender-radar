import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // "standalone": o build gera .next/standalone com um server.js e só os node_modules
  // realmente usados. A imagem Docker copia só isso (imagem pequena, sem npm install).
  output: "standalone",
  // não anunciar "X-Powered-By: Next.js" (informação a menos para quem ataca)
  poweredByHeader: false,
};

export default nextConfig;

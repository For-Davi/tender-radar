// Vitest: roda os testes dos componentes num DOM simulado (jsdom), sem navegador.
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Os testes rodam no fuso de Brasília, o mesmo dos usuários. Isso reproduz o bug
// clássico de datas sem hora ("2026-09-01" lido como UTC vira 31/08 às 21h).
process.env.TZ = "America/Sao_Paulo";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // limpa o DOM e os mocks entre testes: um teste nunca vê o estado de outro
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/lib/**", "src/components/**"],
      exclude: ["src/lib/api/schema.d.ts", "**/*.test.*"],
      reporter: ["text", "html"],
      // mesmo critério do backend: abaixo de 80% o make check falha
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});

// Preparação comum a todos os testes (vitest.config.mts -> setupFiles).
import "@testing-library/jest-dom/vitest"; // matchers como toBeInTheDocument()

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

// MSW: intercepta o fetch e responde com os handlers de src/test/handlers.ts.
// "error": uma requisição sem handler FALHA o teste (nada escapa para a rede real).
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers(); // tira os handlers específicos que um teste adicionou
  cleanup(); // desmonta o que foi renderizado
});
afterAll(() => server.close());

// O Recharts mede o tamanho do contêiner com ResizeObserver, que o jsdom não tem.
class ResizeObserverFalso {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverFalso;

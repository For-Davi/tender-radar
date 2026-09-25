// Renderiza um componente com tudo o que ele precisa em volta (o QueryClient).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import type { ReactElement } from "react";

export function renderComApi(ui: ReactElement): RenderResult & { user: UserEvent } {
  // um cliente novo por teste (sem cache compartilhado) e sem novas tentativas:
  // um erro da API aparece na hora, sem esperar os retries
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return {
    user: userEvent.setup(),
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  };
}

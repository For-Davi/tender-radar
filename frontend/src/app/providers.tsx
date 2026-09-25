"use client";

// Client component: o QueryClient guarda o cache das respostas da API em memória, no
// navegador. Ele é criado uma vez por aba (useState), e não a cada renderização.
import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { criarQueryClient } from "@/lib/api/queries";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(criarQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

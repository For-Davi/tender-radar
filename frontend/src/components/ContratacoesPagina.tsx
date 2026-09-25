"use client";

// Liga a tela de contratações à URL: lê os filtros da query string e, quando eles
// mudam, navega para a nova URL (o histórico do navegador guarda cada busca).
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { filtrosDaUrl, filtrosParaUrl, type Filtros } from "@/lib/filtros";

import { ContratacoesView } from "./ContratacoesView";

export function ContratacoesPagina() {
  const router = useRouter();
  const pathname = usePathname();
  const filtros = filtrosDaUrl(new URLSearchParams(useSearchParams().toString()));

  function navegar(novos: Filtros) {
    const query = filtrosParaUrl(novos);
    // scroll: false mantém a posição ao trocar de página ou de filtro
    router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return <ContratacoesView filtros={filtros} onFiltrosChange={navegar} />;
}

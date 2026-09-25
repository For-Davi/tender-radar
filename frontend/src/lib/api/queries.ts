// Hooks do TanStack Query: um por consulta à API.
//
// O TanStack Query cuida do que todo fetch em tela precisa: estado de carregando e de
// erro, cache (voltar para uma página já vista é instantâneo), deduplicação (dois
// componentes pedindo o mesmo dado = uma requisição) e novas tentativas.
//
// A `queryKey` identifica o dado no cache: filtros diferentes = chaves diferentes.
import { QueryClient, keepPreviousData, useQuery } from "@tanstack/react-query";

import { paraParametros, type Filtros } from "@/lib/filtros";

import { ApiError, api, obter } from "./client";

export function criarQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // os dados mudam no máximo a cada ingestão (1 h): 1 min de cache basta
        staleTime: 60_000,
        // repetir só falhas temporárias (rede, 5xx). 4xx não muda repetindo, e o 503
        // da gold só muda depois de alguém rodar o dbt
        retry: (tentativas, erro) =>
          tentativas < 2 &&
          erro instanceof ApiError &&
          (erro.status === 0 || (erro.status >= 500 && erro.status !== 503)),
      },
    },
  });
}

export function useContratacoes(filtros: Filtros) {
  const query = paraParametros(filtros);
  return useQuery({
    queryKey: ["contratacoes", query],
    queryFn: () => obter(() => api.GET("/contratacoes", { params: { query } })),
    // ao trocar de página, mantém a página anterior na tela até a nova chegar
    placeholderData: keepPreviousData,
  });
}

export function useContratacao(id: string) {
  return useQuery({
    queryKey: ["contratacao", id],
    queryFn: () => obter(() => api.GET("/contratacoes/{id}", { params: { path: { id } } })),
  });
}

/** Só o total (tamanho_pagina=1): o KPI não precisa das linhas. */
export function useTotalContratacoes() {
  return useQuery({
    queryKey: ["contratacoes", "total"],
    queryFn: () =>
      obter(() => api.GET("/contratacoes", { params: { query: { tamanho_pagina: 1 } } })),
    select: (pagina) => pagina.total,
  });
}

/** Órgãos para o select de filtro (os 100 primeiros, em ordem alfabética). */
export function useOrgaos() {
  return useQuery({
    queryKey: ["orgaos"],
    queryFn: () => obter(() => api.GET("/orgaos", { params: { query: { tamanho_pagina: 100 } } })),
  });
}

export function useCategorias() {
  return useQuery({
    queryKey: ["categorias"],
    queryFn: () => obter(() => api.GET("/categorias")),
  });
}

export function useValorMensal() {
  return useQuery({
    queryKey: ["metricas", "valor-mensal"],
    queryFn: () => obter(() => api.GET("/metricas/valor-mensal")),
  });
}

export function useRankingFornecedores() {
  return useQuery({
    queryKey: ["metricas", "ranking-fornecedores"],
    queryFn: () => obter(() => api.GET("/metricas/ranking-fornecedores")),
  });
}

export function useTotalAlertas() {
  return useQuery({
    queryKey: ["metricas", "precos-acima-p90", "total"],
    queryFn: () =>
      obter(() =>
        api.GET("/metricas/precos-acima-p90", { params: { query: { tamanho_pagina: 1 } } }),
      ),
    select: (pagina) => pagina.total,
  });
}

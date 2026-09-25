// Respostas padrão da API falsa (MSW). Cada teste pode trocar uma rota com
// `server.use(...)` para simular um caso (vazio, erro, 503...).
import { http, HttpResponse } from "msw";

import { API_URL, type ProblemDetail } from "@/lib/api/client";

import { CATEGORIAS, ORGAOS, RANKING, VALOR_MENSAL, contratacao, detalhe, pagina } from "./dados";

export const url = (caminho: string) => `${API_URL}${caminho}`;

/** Resposta de erro no formato do backend (application/problem+json). */
export function problema(status: number, detail: string, title = "Erro") {
  const corpo: ProblemDetail = { type: "about:blank", title, status, detail };
  return HttpResponse.json(corpo, {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

export const handlers = [
  http.get(url("/contratacoes"), () =>
    HttpResponse.json(pagina([contratacao(1), contratacao(2)], 2)),
  ),
  http.get(url("/contratacoes/:id"), () => HttpResponse.json(detalhe(1))),
  http.get(url("/orgaos"), () => HttpResponse.json(pagina(ORGAOS, 45, 1, 100))),
  http.get(url("/categorias"), () => HttpResponse.json(CATEGORIAS)),
  http.get(url("/metricas/valor-mensal"), () => HttpResponse.json(VALOR_MENSAL)),
  http.get(url("/metricas/ranking-fornecedores"), () => HttpResponse.json(RANKING)),
  http.get(url("/metricas/precos-acima-p90"), () => HttpResponse.json(pagina([], 15, 1, 1))),
];

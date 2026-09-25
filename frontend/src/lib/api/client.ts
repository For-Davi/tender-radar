// Cliente HTTP da API, tipado pelo schema OpenAPI do backend.
//
// `schema.d.ts` é GERADO (make openapi): cada rota, parâmetro e resposta vira um tipo.
// O openapi-fetch usa esses tipos, então `api.GET("/contratacoes", ...)` só compila se
// a rota existir e os parâmetros estiverem certos, e o `data` já vem com o tipo da resposta.
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type ProblemDetail = Schemas["ProblemDetail"];

// NEXT_PUBLIC_*: o Next copia o valor para o JavaScript do navegador NO BUILD.
// É o endereço que o NAVEGADOR usa para chegar à API (não o da rede do Docker).
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({
  baseUrl: API_URL,
  // Busca o `fetch` global NA HORA de cada chamada. Sem isso, o openapi-fetch guarda o
  // `fetch` que existia na importação deste módulo, e quem troca o fetch depois (o MSW
  // nos testes) é ignorado: os testes chegaram a chamar a API real por causa disso.
  fetch: (request) => globalThis.fetch(request),
});

/** Erro de uma chamada à API, com o problem+json (RFC 9457) quando o backend mandou um. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly problem?: ProblemDetail,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** A gold (dbt) ainda não foi gerada: o backend responde 503 nas métricas. */
  get indisponivel(): boolean {
    return this.status === 503;
  }

  get naoEncontrado(): boolean {
    return this.status === 404;
  }
}

function ehProblem(corpo: unknown): corpo is ProblemDetail {
  return typeof corpo === "object" && corpo !== null && "status" in corpo && "title" in corpo;
}

type Resultado<T> = { data?: T; error?: unknown; response: Response };

/**
 * Executa uma chamada do openapi-fetch e devolve só os dados, ou lança `ApiError`.
 * É o formato que o TanStack Query espera: sucesso = valor, falha = exceção.
 */
export async function obter<T>(chamada: () => Promise<Resultado<T>>): Promise<T> {
  let resultado: Resultado<T>;
  try {
    resultado = await chamada();
  } catch {
    // fetch só lança em falha de rede (API fora do ar, CORS recusado, DNS...)
    throw new ApiError(0, "Não foi possível conectar à API. Verifique se ela está no ar.");
  }
  const { data, error, response } = resultado;
  if (error !== undefined || !response.ok || data === undefined) {
    const problem = ehProblem(error) ? error : undefined;
    const mensagem = problem?.detail ?? problem?.title ?? `Erro ${response.status} na API`;
    throw new ApiError(response.status, mensagem, problem);
  }
  return data;
}

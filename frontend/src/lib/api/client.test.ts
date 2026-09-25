import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { problema, url } from "@/test/handlers";
import { server } from "@/test/server";

import { criarQueryClient } from "./queries";
import { ApiError, api, obter } from "./client";

describe("obter", () => {
  it("devolve os dados tipados em caso de sucesso", async () => {
    const pagina = await obter(() => api.GET("/contratacoes"));

    expect(pagina.total).toBe(2);
    expect(pagina.itens[0]?.id).toBe("07954480000179-1-000001-2026");
  });

  it("envia os parâmetros de query", async () => {
    let recebida: URL | undefined;
    server.use(
      http.get(url("/contratacoes"), ({ request }) => {
        recebida = new URL(request.url);
        return HttpResponse.json({
          itens: [],
          total: 0,
          pagina: 2,
          tamanho_pagina: 5,
          total_paginas: 0,
        });
      }),
    );

    await obter(() =>
      api.GET("/contratacoes", { params: { query: { uf: "CE", pagina: 2, tamanho_pagina: 5 } } }),
    );

    expect(recebida?.searchParams.toString()).toBe("uf=CE&pagina=2&tamanho_pagina=5");
  });

  it("problem+json vira ApiError com status, detail e o problema inteiro", async () => {
    server.use(
      http.get(url("/contratacoes/:id"), () =>
        problema(404, "contratação não encontrada: X", "Not Found"),
      ),
    );

    const erro = await obter(() =>
      api.GET("/contratacoes/{id}", { params: { path: { id: "X" } } }),
    ).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ApiError);
    const apiError = erro as ApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.naoEncontrado).toBe(true);
    expect(apiError.message).toBe("contratação não encontrada: X");
    expect(apiError.problem?.title).toBe("Not Found");
  });

  it("503 da gold é marcado como indisponível", async () => {
    server.use(http.get(url("/categorias"), () => problema(503, "marts não gerados")));

    const erro = await obter(() => api.GET("/categorias")).catch((e: unknown) => e);

    expect((erro as ApiError).indisponivel).toBe(true);
  });

  it("erro sem problem+json usa uma mensagem genérica com o status", async () => {
    server.use(http.get(url("/categorias"), () => new HttpResponse("falhou", { status: 502 })));

    const erro = await obter(() => api.GET("/categorias")).catch((e: unknown) => e);

    expect((erro as ApiError).message).toBe("Erro 502 na API");
    expect((erro as ApiError).problem).toBeUndefined();
  });

  it("falha de rede vira ApiError com status 0 e mensagem amigável", async () => {
    server.use(http.get(url("/categorias"), () => HttpResponse.error()));

    const erro = await obter(() => api.GET("/categorias")).catch((e: unknown) => e);

    expect((erro as ApiError).status).toBe(0);
    expect((erro as ApiError).message).toMatch(/Não foi possível conectar à API/);
  });
});

describe("política de novas tentativas", () => {
  const retry = criarQueryClient().getDefaultOptions().queries?.retry as (
    tentativas: number,
    erro: unknown,
  ) => boolean;

  it.each([
    [0, "rede"],
    [500, "erro interno"],
    [502, "gateway"],
  ])("repete %s (%s) até 2 vezes", (status) => {
    expect(retry(0, new ApiError(status, "x"))).toBe(true);
    expect(retry(1, new ApiError(status, "x"))).toBe(true);
    expect(retry(2, new ApiError(status, "x"))).toBe(false);
  });

  it.each([400, 404, 422, 503])("não repete %s", (status) => {
    expect(retry(0, new ApiError(status, "x"))).toBe(false);
  });

  it("não repete erros que não são da API", () => {
    expect(retry(0, new Error("bug"))).toBe(false);
  });
});

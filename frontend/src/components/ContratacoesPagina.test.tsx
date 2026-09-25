// Testa a LIGAÇÃO entre a URL e a tela. Os hooks do roteador do Next são substituídos
// (são do framework, não código nosso): o que se verifica é que a URL vira filtros e
// que uma mudança de filtro vira a URL certa.
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { pagina } from "@/test/dados";
import { url } from "@/test/handlers";
import { renderComApi } from "@/test/render";
import { server } from "@/test/server";

import { ContratacoesPagina } from "./ContratacoesPagina";

const navegacao = vi.hoisted(() => ({
  push: vi.fn(),
  query: "",
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: navegacao.push }),
  usePathname: () => "/contratacoes",
  useSearchParams: () => new URLSearchParams(navegacao.query),
}));

beforeEach(() => {
  navegacao.push.mockReset();
  navegacao.query = "";
});

describe("ContratacoesPagina", () => {
  it("os filtros da URL chegam à requisição", async () => {
    navegacao.query = "uf=CE&categoria=30&pagina=2&ordenar=-valor_total_estimado";
    let recebida = "";
    server.use(
      http.get(url("/contratacoes"), ({ request }) => {
        recebida = new URL(request.url).search;
        return HttpResponse.json(pagina([], 0));
      }),
    );
    renderComApi(<ContratacoesPagina />);

    await waitFor(() =>
      expect(recebida).toBe(
        "?ordenar=-valor_total_estimado&pagina=2&tamanho_pagina=20&uf=CE&categoria=30",
      ),
    );
  });

  it("mudar um filtro navega para a nova URL (volta à página 1)", async () => {
    navegacao.query = "pagina=3";
    const { user } = renderComApi(<ContratacoesPagina />);
    await screen.findByRole("table");

    await user.selectOptions(screen.getByLabelText("UF"), "SP");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    expect(navegacao.push).toHaveBeenCalledWith("/contratacoes?uf=SP", { scroll: false });
  });

  it("limpar tudo navega para a URL sem query string", async () => {
    navegacao.query = "uf=CE";
    const { user } = renderComApi(<ContratacoesPagina />);
    await screen.findByRole("table");

    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));

    expect(navegacao.push).toHaveBeenCalledWith("/contratacoes", { scroll: false });
  });
});

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { detalhe } from "@/test/dados";
import { problema, url } from "@/test/handlers";
import { renderComApi } from "@/test/render";
import { server } from "@/test/server";

import { DetalheContratacao, urlPncp } from "./DetalheContratacao";

const ID = "07954480000179-1-000001-2026";

describe("DetalheContratacao", () => {
  it("pede a contratação pelo id público", async () => {
    let pedido = "";
    server.use(
      http.get(url("/contratacoes/:id"), ({ params }) => {
        pedido = String(params.id);
        return HttpResponse.json(detalhe(1));
      }),
    );
    renderComApi(<DetalheContratacao id={ID} />);

    await screen.findByRole("heading", { name: "Objeto da contratação 1" });
    expect(pedido).toBe(ID);
  });

  it("mostra carregando e depois o cabeçalho formatado", async () => {
    renderComApi(<DetalheContratacao id={ID} />);

    expect(screen.getByRole("status")).toHaveTextContent("Carregando contratação…");
    await screen.findByRole("heading", { name: "Objeto da contratação 1" });
    expect(screen.getByText("ESTADO DO CEARA (07.954.480/0001-79)")).toBeInTheDocument();
    expect(screen.getByText("24/09/2026, 17:31")).toBeInTheDocument();
    expect(screen.getByText(/R\$\s1\.500,50/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver no PNCP" })).toHaveAttribute(
      "href",
      "https://pncp.gov.br/app/editais/07954480000179/2026/1",
    );
  });

  it("itens: com e sem vencedor, sigiloso e quantidades em pt-BR", async () => {
    renderComApi(<DetalheContratacao id={ID} />);

    const tabela = await screen.findByRole("table", { name: "Itens (2)" });
    const [, item1, item2] = within(tabela).getAllByRole("row");

    const primeiro = within(item1!);
    expect(primeiro.getByText("1.000 Comprimido")).toBeInTheDocument();
    expect(primeiro.getByText(/R\$\s0,50/)).toBeInTheDocument();
    expect(primeiro.getByText(/R\$\s500,00/)).toBeInTheDocument();
    expect(primeiro.getByText("Sem resultado")).toBeInTheDocument();
    expect(primeiro.getByText(/NCM 30049099/)).toBeInTheDocument();

    const segundo = within(item2!);
    expect(segundo.getAllByText("Sigiloso")).toHaveLength(2); // unitário e total
    expect(segundo.getByText("Farmácia Exemplo Ltda")).toBeInTheDocument();
    expect(segundo.getByText(/Homologado: R\$\s1,20 \/ un\./)).toBeInTheDocument();
  });

  it("contratação sem itens mostra estado vazio", async () => {
    server.use(
      http.get(url("/contratacoes/:id"), () => HttpResponse.json({ ...detalhe(1), itens: [] })),
    );
    renderComApi(<DetalheContratacao id={ID} />);

    expect(
      await screen.findByText("Esta contratação não tem itens publicados."),
    ).toBeInTheDocument();
  });

  it("404: mostra 'não encontrada' com link para a lista", async () => {
    server.use(
      http.get(url("/contratacoes/:id"), () => problema(404, "contratação não encontrada")),
    );
    renderComApi(<DetalheContratacao id={ID} />);

    expect(await screen.findByText(/Contratação não encontrada/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar para a lista" })).toHaveAttribute(
      "href",
      "/contratacoes",
    );
    expect(screen.queryByRole("alert")).toBeNull(); // não é erro do sistema
  });

  it("422 (id malformado na URL) mostra o erro da API", async () => {
    server.use(http.get(url("/contratacoes/:id"), () => problema(422, "parâmetros inválidos")));
    renderComApi(<DetalheContratacao id="abc" />);

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível carregar a contratação");
    expect(alerta).toHaveTextContent("parâmetros inválidos");
  });
});

describe("urlPncp", () => {
  it("monta o link do edital no PNCP (sequencial sem zeros)", () => {
    expect(urlPncp("07954480000179-1-024883/2026")).toBe(
      "https://pncp.gov.br/app/editais/07954480000179/2026/24883",
    );
  });

  it("número malformado não gera link", () => {
    expect(urlPncp("qualquer")).toBeNull();
  });
});

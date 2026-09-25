import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { FILTROS_VAZIOS, type Filtros } from "@/lib/filtros";
import { CNPJ_CE, contratacao, pagina } from "@/test/dados";
import { problema, url } from "@/test/handlers";
import { renderComApi } from "@/test/render";
import { server } from "@/test/server";

import { ContratacoesView } from "./ContratacoesView";

/** Faz o papel da página: guarda os filtros num estado (na app real, é a URL). */
function ComEstado({ inicial = FILTROS_VAZIOS }: { inicial?: Filtros }) {
  const [filtros, setFiltros] = useState(inicial);
  return <ContratacoesView filtros={filtros} onFiltrosChange={setFiltros} />;
}

/**
 * Registra as requisições a /contratacoes. A resposta simula 45 contratações
 * (3 páginas de 20), respeitando a página pedida.
 */
function capturarRequisicoes(total = 45) {
  const recebidas: URLSearchParams[] = [];
  server.use(
    http.get(url("/contratacoes"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      recebidas.push(params);
      const numero = Number(params.get("pagina") ?? 1);
      const quantidade = Math.max(0, Math.min(20, total - (numero - 1) * 20));
      const itens = Array.from({ length: quantidade }, (_, i) =>
        contratacao((numero - 1) * 20 + i + 1),
      );
      return HttpResponse.json(pagina(itens, total, numero, 20));
    }),
  );
  /** Query string da última requisição, sem os parâmetros fixos de paginação. */
  const ultima = () => {
    const params = new URLSearchParams(recebidas.at(-1));
    params.delete("tamanho_pagina");
    return Object.fromEntries(params);
  };
  return { recebidas, ultima };
}

async function esperarTabela() {
  return screen.findByRole("table", { name: "Contratações encontradas" });
}

describe("ContratacoesView — lista", () => {
  it("mostra carregando e depois a tabela com valores e datas em pt-BR", async () => {
    server.use(
      http.get(url("/contratacoes"), () =>
        HttpResponse.json(
          pagina([contratacao(1), contratacao(2, { valor_total_estimado: null })], 2),
        ),
      ),
    );
    renderComApi(<ComEstado />);

    expect(screen.getByRole("status")).toHaveTextContent("Carregando contratações…");
    const tabela = await esperarTabela();
    const linhas = within(tabela).getAllByRole("row");
    expect(linhas).toHaveLength(3); // cabeçalho + 2
    const primeira = within(linhas[1]!);
    // 20:31 UTC = 17:31 em Brasília
    expect(primeira.getByText("24/09/2026, 17:31")).toBeInTheDocument();
    expect(primeira.getByText(/R\$\s1\.500,50/)).toBeInTheDocument();
    expect(primeira.getByRole("link", { name: "Objeto da contratação 1" })).toHaveAttribute(
      "href",
      "/contratacoes/07954480000179-1-000001-2026",
    );
    expect(within(linhas[2]!).getByText("Sigiloso")).toBeInTheDocument();
  });

  it("a primeira requisição usa os padrões (página 1, mais recentes)", async () => {
    const { ultima } = capturarRequisicoes();
    renderComApi(<ComEstado />);

    await esperarTabela();
    expect(ultima()).toEqual({ ordenar: "-data_publicacao", pagina: "1" });
  });
});

describe("ContratacoesView — filtros alteram a requisição", () => {
  it("UF", async () => {
    const { ultima } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await esperarTabela();

    await user.selectOptions(screen.getByLabelText("UF"), "CE");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(ultima()).toMatchObject({ uf: "CE" }));
  });

  it("órgão (select preenchido pela API)", async () => {
    const { ultima } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await screen.findByRole("option", { name: "ESTADO DO CEARA" });

    await user.selectOptions(screen.getByLabelText("Órgão"), "ESTADO DO CEARA");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(ultima()).toMatchObject({ orgao: CNPJ_CE }));
  });

  it("categoria: só as classificadas (com capítulo NCM) aparecem", async () => {
    const { ultima } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await screen.findByRole("option", { name: "30 - Produtos farmacêuticos" });

    expect(screen.queryByRole("option", { name: "Material sem classificação" })).toBeNull();
    await user.selectOptions(screen.getByLabelText("Categoria"), "30 - Produtos farmacêuticos");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(ultima()).toMatchObject({ categoria: "30" }));
  });

  it("filtros combinados vão juntos na mesma requisição", async () => {
    const { ultima } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await esperarTabela();

    await user.selectOptions(screen.getByLabelText("UF"), "CE");
    await user.type(screen.getByLabelText("Publicada a partir de"), "2026-09-01");
    await user.type(screen.getByLabelText("Publicada até"), "2026-09-30");
    await user.type(screen.getByLabelText("Valor mínimo (R$)"), "1000");
    await user.type(screen.getByLabelText("Valor máximo (R$)"), "50000.5");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() =>
      expect(ultima()).toEqual({
        uf: "CE",
        data_inicio: "2026-09-01",
        data_fim: "2026-09-30",
        valor_min: "1000",
        valor_max: "50000.5",
        ordenar: "-data_publicacao",
        pagina: "1",
      }),
    );
  });

  it("ordenação muda a requisição na hora", async () => {
    const { ultima } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await esperarTabela();

    await user.selectOptions(screen.getByLabelText("Ordenar por"), "Maior valor");

    await waitFor(() => expect(ultima()).toMatchObject({ ordenar: "-valor_total_estimado" }));
  });

  it("limpar filtros volta à requisição sem filtros", async () => {
    const { ultima } = capturarRequisicoes();
    const { user } = renderComApi(
      <ComEstado inicial={{ ...FILTROS_VAZIOS, uf: "SP", categoria: "30" }} />,
    );
    await esperarTabela();
    expect(ultima()).toMatchObject({ uf: "SP", categoria: "30" });

    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => expect(ultima()).toEqual({ ordenar: "-data_publicacao", pagina: "1" }));
    expect(screen.getByLabelText("UF")).toHaveValue("");
  });

  it("datas invertidas: avisa e não consulta a API", async () => {
    const { recebidas } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await esperarTabela();
    const antes = recebidas.length;

    await user.type(screen.getByLabelText("Publicada a partir de"), "2026-09-30");
    await user.type(screen.getByLabelText("Publicada até"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    expect(screen.getByRole("alert")).toHaveTextContent("A data inicial não pode ser depois");
    expect(recebidas).toHaveLength(antes);
  });

  it("valores invertidos: avisa e não consulta a API", async () => {
    const { recebidas } = capturarRequisicoes();
    const { user } = renderComApi(<ComEstado />);
    await esperarTabela();
    const antes = recebidas.length;

    await user.type(screen.getByLabelText("Valor mínimo (R$)"), "500");
    await user.type(screen.getByLabelText("Valor máximo (R$)"), "100");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    expect(screen.getByRole("alert")).toHaveTextContent("O valor mínimo não pode ser maior");
    expect(recebidas).toHaveLength(antes);
  });

  it("categorias indisponíveis (gold sem dbt) não impedem a busca", async () => {
    server.use(http.get(url("/categorias"), () => problema(503, "marts não gerados")));
    renderComApi(<ComEstado />);

    await esperarTabela();
    await waitFor(() => expect(screen.getByLabelText("Categoria")).toBeDisabled());
    expect(screen.getByRole("option", { name: "Indisponível" })).toBeInTheDocument();
  });
});

describe("ContratacoesView — paginação", () => {
  it("próxima e anterior pedem a página certa; bordas desabilitadas", async () => {
    const { ultima } = capturarRequisicoes(45);
    const { user } = renderComApi(<ComEstado />);
    await esperarTabela();

    expect(screen.getByText("Página 1 de 3 · 45 resultados")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Próxima" }));
    await screen.findByText("Página 2 de 3 · 45 resultados");
    expect(ultima()).toMatchObject({ pagina: "2" });

    await user.click(screen.getByRole("button", { name: "Próxima" }));
    await screen.findByText("Página 3 de 3 · 45 resultados");
    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
    // a última página tem só 5 linhas (45 - 40)
    expect(within(await esperarTabela()).getAllByRole("row")).toHaveLength(6);

    await user.click(screen.getByRole("button", { name: "Anterior" }));
    await screen.findByText("Página 2 de 3 · 45 resultados");
  });

  it("mudar um filtro na página 2 volta para a página 1", async () => {
    const { ultima } = capturarRequisicoes(45);
    const { user } = renderComApi(<ComEstado inicial={{ ...FILTROS_VAZIOS, pagina: 2 }} />);
    await screen.findByText("Página 2 de 3 · 45 resultados");

    await user.selectOptions(screen.getByLabelText("UF"), "CE");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(ultima()).toMatchObject({ uf: "CE", pagina: "1" }));
  });

  it("página além da última (URL antiga): mensagem, e 'Próxima' desabilitado", async () => {
    capturarRequisicoes(45);
    renderComApi(<ComEstado inicial={{ ...FILTROS_VAZIOS, pagina: 9 }} />);

    expect(await screen.findByText(/Esta página não existe mais/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
  });
});

describe("ContratacoesView — vazio e erro", () => {
  it("vazio com filtro: sugere mudar o filtro", async () => {
    capturarRequisicoes(0);
    renderComApi(<ComEstado inicial={{ ...FILTROS_VAZIOS, uf: "RR" }} />);

    expect(await screen.findByText("Nenhuma contratação para estes filtros.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Paginação" })).toBeNull();
  });

  it("vazio sem filtro: explica que ainda não há dados", async () => {
    capturarRequisicoes(0);
    renderComApi(<ComEstado />);

    expect(await screen.findByText(/Ainda não há contratações/)).toBeInTheDocument();
  });

  it("erro da API: mostra o detail do problem+json", async () => {
    server.use(
      http.get(url("/contratacoes"), () =>
        problema(500, "erro interno; tente novamente mais tarde"),
      ),
    );
    renderComApi(<ComEstado />);

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Não foi possível buscar as contratações");
    expect(alerta).toHaveTextContent("erro interno; tente novamente mais tarde");
  });

  it("API fora do ar: mensagem de conexão", async () => {
    server.use(http.get(url("/contratacoes"), () => HttpResponse.error()));
    renderComApi(<ComEstado />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível conectar à API");
  });
});

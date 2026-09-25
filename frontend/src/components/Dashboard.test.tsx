import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { RANKING, VALOR_MENSAL } from "@/test/dados";
import { problema, url } from "@/test/handlers";
import { renderComApi } from "@/test/render";
import { server } from "@/test/server";

import { Dashboard } from "./Dashboard";
import { agregarFornecedores } from "./GraficoFornecedores";

const semNbsp = (texto: string | null) => (texto ?? "").replace(/ /g, " ");

/** Valor exibido de um KPI, localizado pelo título. */
async function kpi(titulo: string) {
  const termo = await screen.findByText(titulo, { selector: "dt" });
  const bloco = termo.parentElement as HTMLElement;
  await waitFor(() =>
    expect(within(bloco).getAllByRole("definition")[0]).not.toHaveTextContent("…"),
  );
  return semNbsp(within(bloco).getAllByRole("definition")[0]!.textContent);
}

describe("Dashboard — KPIs", () => {
  it("mostra os 4 números formatados em pt-BR", async () => {
    server.use(
      http.get(url("/contratacoes"), () =>
        HttpResponse.json({
          itens: [],
          total: 1140,
          pagina: 1,
          tamanho_pagina: 1,
          total_paginas: 1140,
        }),
      ),
    );
    renderComApi(<Dashboard />);

    expect(await kpi("Contratações")).toBe("1.140");
    // 1.000.000 + 148.851.981,79 = R$ 149,9 mi
    expect(await kpi("Valor estimado total")).toBe("R$ 149,9 mi");
    expect(await kpi("Órgãos")).toBe("45");
    expect(await kpi("Preços acima do p90")).toBe("15");
  });

  it("enquanto carrega, os KPIs mostram reticências e ficam 'ocupados'", () => {
    renderComApi(<Dashboard />);

    const valores = screen.getAllByText("…");
    expect(valores).toHaveLength(4);
    for (const valor of valores) expect(valor).toHaveAttribute("aria-busy", "true");
  });

  it("gold indisponível (503): métricas avisam, KPIs da silver continuam", async () => {
    const indisponivel = () => problema(503, "camada analítica indisponível");
    server.use(
      http.get(url("/metricas/valor-mensal"), indisponivel),
      http.get(url("/metricas/precos-acima-p90"), indisponivel),
      http.get(url("/metricas/ranking-fornecedores"), indisponivel),
    );
    renderComApi(<Dashboard />);

    expect(await kpi("Contratações")).toBe("2");
    expect(await kpi("Órgãos")).toBe("45");
    expect(await kpi("Valor estimado total")).toBe("Indisponível");
    expect(await kpi("Preços acima do p90")).toBe("Indisponível");
    // os dois gráficos explicam o que fazer
    const alertas = await screen.findAllByRole("alert");
    expect(alertas).toHaveLength(2);
    for (const alerta of alertas) expect(alerta).toHaveTextContent("Rode make dbt");
  });

  it("API fora do ar: todos os blocos mostram erro, sem quebrar a página", async () => {
    server.use(http.get(`${url("")}/*`, () => HttpResponse.error()));
    renderComApi(<Dashboard />);

    expect(await kpi("Contratações")).toBe("Indisponível");
    expect(screen.getByRole("heading", { name: "Painel" })).toBeInTheDocument();
    expect(await screen.findAllByRole("alert")).toHaveLength(2);
  });
});

describe("Dashboard — gráfico mensal", () => {
  it("tabela acessível com meses e valores em pt-BR", async () => {
    renderComApi(<Dashboard />);

    const tabela = await screen.findByRole("table", {
      name: "Valor contratado por mês (dados do gráfico)",
    });
    const linhas = within(tabela)
      .getAllByRole("row")
      .map((l) => semNbsp(l.textContent));
    expect(linhas).toEqual([
      "MêsContrataçõesValor estimadoMédia móvel de 3 meses",
      "ago/202610R$ 1.000.000,00R$ 1.000.000,00 (1 mês)",
      "set/2026114R$ 148.851.981,79R$ 74.925.990,89 (2 meses)",
    ]);
    expect(screen.getByRole("figure", { name: "Valor contratado por mês" })).toBeInTheDocument();
  });

  it("série vazia mostra estado vazio", async () => {
    server.use(http.get(url("/metricas/valor-mensal"), () => HttpResponse.json([])));
    renderComApi(<Dashboard />);

    expect(await screen.findByText("Ainda não há meses com contratações.")).toBeInTheDocument();
  });

  it("média com 3 meses não leva a observação", async () => {
    server.use(
      http.get(url("/metricas/valor-mensal"), () =>
        HttpResponse.json([{ ...VALOR_MENSAL[0]!, meses_na_media: 3 }]),
      ),
    );
    renderComApi(<Dashboard />);

    const tabela = await screen.findByRole("table", { name: /Valor contratado por mês/ });
    expect(within(tabela).queryByText(/mês\)|meses\)/)).toBeNull();
  });
});

describe("Dashboard — top fornecedores", () => {
  it("tabela acessível do maior para o menor", async () => {
    renderComApi(<Dashboard />);

    const tabela = await screen.findByRole("table", {
      name: "Top fornecedores por valor homologado (dados do gráfico)",
    });
    const nomes = within(tabela)
      .getAllByRole("rowheader")
      .map((c) => c.textContent);
    expect(nomes).toEqual(["GARAGE MIDIA VISUAL LTDA", "CLAUDINO INDUSTRIA GRAFICA"]);
    expect(semNbsp(within(tabela).getAllByRole("row")[1]!.textContent)).toContain("R$ 40.500,00");
  });

  it("sem vencedores ainda: estado vazio", async () => {
    server.use(http.get(url("/metricas/ranking-fornecedores"), () => HttpResponse.json([])));
    renderComApi(<Dashboard />);

    expect(
      await screen.findByText("Nenhum item com vencedor homologado ainda."),
    ).toBeInTheDocument();
  });
});

describe("Dashboard — tabelas acessíveis dos gráficos", () => {
  it("o sr-only fica numa div em volta, nunca na própria <table>", async () => {
    // bug visto no navegador real: <table class="sr-only"> ignora width: 1px (tabela não
    // encolhe abaixo do conteúdo) e criava uma rolagem horizontal invisível no painel
    renderComApi(<Dashboard />);

    const tabelas = [
      await screen.findByRole("table", { name: /Valor contratado por mês/ }),
      await screen.findByRole("table", { name: /Top fornecedores/ }),
    ];
    for (const tabela of tabelas) {
      expect(tabela).not.toHaveClass("sr-only");
      expect(tabela.parentElement).toHaveClass("sr-only");
    }
  });
});

describe("agregarFornecedores", () => {
  const linha = RANKING[0]!;

  it("soma o mesmo fornecedor em órgãos diferentes", () => {
    const [total] = agregarFornecedores([
      linha,
      { ...linha, orgao_cnpj: "outro", valor_total_homologado: "500.0000", itens_vencidos: 2 },
    ]);

    expect(total).toEqual({
      documento: linha.fornecedor_documento,
      nome: linha.fornecedor_nome,
      valor: 41000,
      itens: 5,
      orgaos: 2,
    });
  });

  it("ordena por valor e desempata pelo nome; respeita o limite", () => {
    const linhas = ["C", "A", "B"].map((nome, i) => ({
      ...linha,
      fornecedor_documento: nome,
      fornecedor_nome: nome,
      valor_total_homologado: i === 0 ? "999" : "100",
    }));

    expect(agregarFornecedores(linhas).map((f) => f.nome)).toEqual(["C", "A", "B"]);
    expect(agregarFornecedores(linhas, 2)).toHaveLength(2);
  });
});

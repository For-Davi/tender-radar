import { describe, expect, it } from "vitest";

import {
  FILTROS_VAZIOS,
  TAMANHO_PAGINA,
  alterarFiltros,
  filtrosDaUrl,
  filtrosParaUrl,
  paraParametros,
  temFiltroAtivo,
  type Filtros,
} from "./filtros";

const url = (query: string) => new URLSearchParams(query);

describe("filtrosDaUrl", () => {
  it("sem query string: filtros padrão", () => {
    expect(filtrosDaUrl(url(""))).toEqual(FILTROS_VAZIOS);
  });

  it("lê todos os campos", () => {
    const filtros = filtrosDaUrl(
      url(
        "uf=CE&orgao=07954480000179&categoria=30&data_inicio=2026-09-01&data_fim=2026-09-30" +
          "&valor_min=100&valor_max=5000&ordenar=-valor_total_estimado&pagina=3",
      ),
    );

    expect(filtros).toEqual<Filtros>({
      uf: "CE",
      orgao: "07954480000179",
      categoria: "30",
      data_inicio: "2026-09-01",
      data_fim: "2026-09-30",
      valor_min: "100",
      valor_max: "5000",
      ordenar: "-valor_total_estimado",
      pagina: 3,
    });
  });

  it.each(["0", "-1", "abc", "1.5"])("página inválida (%s) vira 1", (pagina) => {
    expect(filtrosDaUrl(url(`pagina=${pagina}`)).pagina).toBe(1);
  });

  it("ordenação desconhecida vira a padrão", () => {
    expect(filtrosDaUrl(url("ordenar=objeto")).ordenar).toBe("-data_publicacao");
  });
});

describe("filtrosParaUrl", () => {
  it("padrão gera query vazia", () => {
    expect(filtrosParaUrl(FILTROS_VAZIOS)).toBe("");
  });

  it("só inclui o que difere do padrão, sem espaços", () => {
    const query = filtrosParaUrl({ ...FILTROS_VAZIOS, uf: " CE ", pagina: 2 });

    expect(query).toBe("uf=CE&pagina=2");
  });

  it("ida e volta preserva os filtros", () => {
    const filtros: Filtros = {
      ...FILTROS_VAZIOS,
      categoria: "30",
      valor_max: "1000",
      ordenar: "valor_total_estimado",
      pagina: 4,
    };

    expect(filtrosDaUrl(url(filtrosParaUrl(filtros)))).toEqual(filtros);
  });
});

describe("alterarFiltros", () => {
  const naPagina3: Filtros = { ...FILTROS_VAZIOS, pagina: 3 };

  it("mudar um filtro volta para a página 1", () => {
    expect(alterarFiltros(naPagina3, { uf: "SP" })).toEqual({
      ...FILTROS_VAZIOS,
      uf: "SP",
      pagina: 1,
    });
  });

  it("mudar a ordenação também volta para a página 1", () => {
    expect(alterarFiltros(naPagina3, { ordenar: "data_publicacao" }).pagina).toBe(1);
  });

  it("mudar só a página mantém os filtros", () => {
    const comUf = { ...naPagina3, uf: "CE" };

    expect(alterarFiltros(comUf, { pagina: 4 })).toEqual({ ...comUf, pagina: 4 });
  });
});

describe("paraParametros", () => {
  it("campos vazios não são enviados à API", () => {
    expect(paraParametros(FILTROS_VAZIOS)).toEqual({
      ordenar: "-data_publicacao",
      pagina: 1,
      tamanho_pagina: TAMANHO_PAGINA,
    });
  });

  it("envia os filtros preenchidos", () => {
    const parametros = paraParametros({ ...FILTROS_VAZIOS, uf: "CE", valor_min: "10" });

    expect(parametros).toMatchObject({ uf: "CE", valor_min: "10" });
    expect(parametros).not.toHaveProperty("orgao");
  });
});

describe("temFiltroAtivo", () => {
  it("ordenação e página não contam como filtro", () => {
    expect(temFiltroAtivo({ ...FILTROS_VAZIOS, pagina: 2, ordenar: "data_publicacao" })).toBe(
      false,
    );
    expect(temFiltroAtivo({ ...FILTROS_VAZIOS, uf: "CE" })).toBe(true);
  });
});

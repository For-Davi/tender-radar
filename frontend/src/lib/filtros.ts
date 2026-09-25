// Filtros da lista de contratações e a conversão de/para a URL.
//
// Os filtros moram na URL (/contratacoes?uf=CE&pagina=2): um link compartilhado
// reproduz a busca e o botão "voltar" do navegador desfaz a última mudança.
import type { paths } from "@/lib/api/schema";

/** Parâmetros aceitos por GET /contratacoes (tipo gerado do OpenAPI). */
export type ParametrosContratacoes = NonNullable<
  paths["/contratacoes"]["get"]["parameters"]["query"]
>;

export type Ordenacao = NonNullable<ParametrosContratacoes["ordenar"]>;

export const ORDENACAO_PADRAO: Ordenacao = "-data_publicacao";
export const TAMANHO_PAGINA = 20;

export const ORDENACOES: { valor: Ordenacao; rotulo: string }[] = [
  { valor: "-data_publicacao", rotulo: "Mais recentes" },
  { valor: "data_publicacao", rotulo: "Mais antigas" },
  { valor: "-valor_total_estimado", rotulo: "Maior valor" },
  { valor: "valor_total_estimado", rotulo: "Menor valor" },
];

/** Estado dos filtros na tela. Texto vazio = sem filtro. */
export interface Filtros {
  uf: string;
  orgao: string;
  categoria: string;
  data_inicio: string;
  data_fim: string;
  valor_min: string;
  valor_max: string;
  ordenar: Ordenacao;
  pagina: number;
}

export const FILTROS_VAZIOS: Filtros = {
  uf: "",
  orgao: "",
  categoria: "",
  data_inicio: "",
  data_fim: "",
  valor_min: "",
  valor_max: "",
  ordenar: ORDENACAO_PADRAO,
  pagina: 1,
};

const CAMPOS_TEXTO = [
  "uf",
  "orgao",
  "categoria",
  "data_inicio",
  "data_fim",
  "valor_min",
  "valor_max",
] as const;

function ehOrdenacao(valor: string | null): valor is Ordenacao {
  return ORDENACOES.some((o) => o.valor === valor);
}

/** URL -> filtros. Valores desconhecidos ou malformados caem no padrão. */
export function filtrosDaUrl(params: URLSearchParams): Filtros {
  const filtros: Filtros = { ...FILTROS_VAZIOS };
  for (const campo of CAMPOS_TEXTO) {
    filtros[campo] = params.get(campo)?.trim() ?? "";
  }
  const ordenar = params.get("ordenar");
  if (ehOrdenacao(ordenar)) filtros.ordenar = ordenar;
  const pagina = Number(params.get("pagina"));
  if (Number.isInteger(pagina) && pagina >= 1) filtros.pagina = pagina;
  return filtros;
}

/** Filtros -> query string. Só vai o que difere do padrão (URL curta e legível). */
export function filtrosParaUrl(filtros: Filtros): string {
  const params = new URLSearchParams();
  for (const campo of CAMPOS_TEXTO) {
    const valor = filtros[campo].trim();
    if (valor) params.set(campo, valor);
  }
  if (filtros.ordenar !== ORDENACAO_PADRAO) params.set("ordenar", filtros.ordenar);
  if (filtros.pagina > 1) params.set("pagina", String(filtros.pagina));
  return params.toString();
}

/** Muda filtros. Mudar qualquer filtro volta para a página 1 (a antiga pode nem existir). */
export function alterarFiltros(atual: Filtros, mudanca: Partial<Filtros>): Filtros {
  const mudouPagina = mudanca.pagina !== undefined;
  return { ...atual, ...mudanca, pagina: mudouPagina ? (mudanca.pagina ?? 1) : 1 };
}

/** Filtros -> parâmetros da API. Campo vazio não é enviado. */
export function paraParametros(filtros: Filtros): ParametrosContratacoes {
  const parametros: ParametrosContratacoes = {
    ordenar: filtros.ordenar,
    pagina: filtros.pagina,
    tamanho_pagina: TAMANHO_PAGINA,
  };
  for (const campo of CAMPOS_TEXTO) {
    const valor = filtros[campo].trim();
    if (valor) parametros[campo] = valor;
  }
  return parametros;
}

export function temFiltroAtivo(filtros: Filtros): boolean {
  return CAMPOS_TEXTO.some((campo) => filtros[campo].trim() !== "");
}

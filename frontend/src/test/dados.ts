// Respostas de exemplo da API, tipadas pelo schema gerado do OpenAPI: se o backend
// mudar um campo, estes dados deixam de compilar e o teste avisa na hora.
import type { Schemas } from "@/lib/api/client";

type Contratacao = Schemas["ContratacaoResponse"];

export const CNPJ_CE = "07954480000179";

export function contratacao(n: number, extra: Partial<Contratacao> = {}): Contratacao {
  const seq = String(n).padStart(6, "0");
  return {
    id: `${CNPJ_CE}-1-${seq}-2026`,
    numero_controle_pncp: `${CNPJ_CE}-1-${seq}/2026`,
    orgao: { cnpj: CNPJ_CE, razao_social: "ESTADO DO CEARA" },
    modalidade: 6,
    modalidade_nome: "Pregão eletrônico",
    situacao: 1,
    situacao_nome: "Divulgada no PNCP",
    objeto: `Objeto da contratação ${n}`,
    valor_total_estimado: "1500.5000",
    data_publicacao: "2026-09-24T20:31:29Z",
    uf: "CE",
    municipio: "Fortaleza",
    total_itens: 2,
    ...extra,
  };
}

export function pagina<T>(itens: T[], total: number, numero = 1, tamanho = 20) {
  return {
    itens,
    total,
    pagina: numero,
    tamanho_pagina: tamanho,
    total_paginas: Math.ceil(total / tamanho),
  };
}

export function detalhe(n = 1): Schemas["ContratacaoDetalheResponse"] {
  return {
    ...contratacao(n),
    itens: [
      {
        numero_item: 1,
        descricao: "Dipirona 500mg",
        material_ou_servico: "M",
        material_ou_servico_nome: "Material",
        ncm_nbs: "30049099",
        quantidade: "1000.0000",
        unidade_medida: "Comprimido",
        valor_unitario_estimado: "0.5000",
        valor_total_estimado: "500.0000",
        vencedor: null,
        valor_unitario_homologado: null,
      },
      {
        numero_item: 2,
        descricao: "Seringa 5ml",
        material_ou_servico: "M",
        material_ou_servico_nome: "Material",
        ncm_nbs: null,
        quantidade: "10.0000",
        unidade_medida: "Unidade",
        valor_unitario_estimado: null, // sigiloso
        valor_total_estimado: null,
        vencedor: {
          documento: "12ABC34501DE35",
          nome: "Farmácia Exemplo Ltda",
          tipo_pessoa: "PJ",
          tipo_pessoa_nome: "Pessoa jurídica",
        },
        valor_unitario_homologado: "1.2000",
      },
    ],
  };
}

export const ORGAOS: Schemas["OrgaoResponse"][] = [
  {
    cnpj: CNPJ_CE,
    razao_social: "ESTADO DO CEARA",
    esfera: "E",
    esfera_nome: "Estadual",
    poder: "E",
    poder_nome: "Executivo",
    total_contratacoes: 49,
  },
  {
    cnpj: "07982036000100",
    razao_social: "MUNICIPIO DE GRANJA",
    esfera: "M",
    esfera_nome: "Municipal",
    poder: "E",
    poder_nome: "Executivo",
    total_contratacoes: 3,
  },
];

export const CATEGORIAS: Schemas["CategoriaResponse"][] = [
  { material_ou_servico: "M", ncm_capitulo: null, nome: "Material sem classificação" },
  { material_ou_servico: "M", ncm_capitulo: "30", nome: "30 - Produtos farmacêuticos" },
  { material_ou_servico: "M", ncm_capitulo: "90", nome: "90 - Instrumentos médicos" },
];

export const VALOR_MENSAL: Schemas["ValorMensalResponse"][] = [
  {
    mes: "2026-08-01",
    contratacoes: 10,
    itens: 50,
    valor_total_estimado: "1000000.0000",
    media_movel_3m: "1000000.00",
    meses_na_media: 1,
  },
  {
    mes: "2026-09-01",
    contratacoes: 114,
    itens: 1010,
    valor_total_estimado: "148851981.7888",
    media_movel_3m: "74925990.89",
    meses_na_media: 2,
  },
];

export const RANKING: Schemas["RankingFornecedorResponse"][] = [
  {
    orgao_cnpj: "07982036000100",
    orgao_razao_social: "MUNICIPIO DE GRANJA",
    fornecedor_documento: "11444777000161",
    fornecedor_nome: "GARAGE MIDIA VISUAL LTDA",
    itens_vencidos: 3,
    valor_total_homologado: "40500.0000",
    ranking: 1,
    participacao_percentual: "97.59",
  },
  {
    orgao_cnpj: "07982036000100",
    orgao_razao_social: "MUNICIPIO DE GRANJA",
    fornecedor_documento: "12ABC34501DE35",
    fornecedor_nome: "CLAUDINO INDUSTRIA GRAFICA",
    itens_vencidos: 1,
    valor_total_homologado: "1000.0000",
    ranking: 2,
    participacao_percentual: "2.41",
  },
];

# API do PNCP — endpoints usados e peculiaridades

O PNCP (Portal Nacional de Contratações Públicas, Lei 14.133/2021) tem uma API pública,
sem autenticação, com duas bases:

| Base | Uso no projeto |
|---|---|
| `https://pncp.gov.br/api/consulta` | Consulta (busca) de contratações por período |
| `https://pncp.gov.br/api/pncp` | Detalhes de uma contratação: itens, resultados, arquivos |

Documentação oficial (Swagger): `https://pncp.gov.br/api/consulta/swagger-ui/index.html` e
`https://pncp.gov.br/api/pncp/swagger-ui/index.html`.

## Endpoints usados

### 1. Contratações publicadas num período

```
GET /api/consulta/v1/contratacoes/publicacao
    ?dataInicial=20250901&dataFinal=20250901     (AAAAMMDD)
    &codigoModalidadeContratacao=6               (OBRIGATÓRIO)
    &uf=CE                                       (opcional)
    &pagina=1&tamanhoPagina=50                   (máximo 50)
```

Resposta (resumida):

```json
{
  "data": [ { "numeroControlePNCP": "13183513000127-1-000173/2025",
              "orgaoEntidade": {"cnpj": "13183513000127", "razaoSocial": "...", "esferaId": "M", "poderId": "E"},
              "unidadeOrgao": {"ufSigla": "RS", "municipioNome": "Sapucaia do Sul", "codigoIbge": "4320008"},
              "anoCompra": 2025, "sequencialCompra": 173,
              "modalidadeId": 6, "situacaoCompraId": 1,
              "objetoCompra": "...", "valorTotalEstimado": 215264.88, "valorTotalHomologado": 200733.6,
              "dataPublicacaoPncp": "2025-09-01T00:00:47", "...": "dezenas de outros campos" } ],
  "totalRegistros": 1576, "totalPaginas": 158, "numeroPagina": 1, "paginasRestantes": 157, "empty": false
}
```

### 2. Itens de uma contratação

```
GET /api/pncp/v1/orgaos/{cnpj}/compras/{anoCompra}/{sequencialCompra}/itens
```

Lista de itens: `numeroItem`, `descricao`, `materialOuServico` (M/S), `quantidade`,
`unidadeMedida`, `valorUnitarioEstimado`, `itemCategoriaNome`, **`temResultado`**...

### 3. Resultados (vencedores) de um item

```
GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens/{numeroItem}/resultados
```

Lista de resultados: `niFornecedor` (CNPJ/CPF), `tipoPessoa` (PJ/PF/PE),
`nomeRazaoSocialFornecedor`, `valorUnitarioHomologado`, `quantidadeHomologada`...
Só é consultado para itens com `temResultado: true`.

### 4. Arquivos (documentos) de uma contratação

```
GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos
```

Lista: `sequencialDocumento`, `tipoDocumentoId` (**2 = Edital**), `tipoDocumentoNome`,
`titulo`, `url`. A `url` baixa o arquivo.

## Peculiaridades verificadas (2026-09-24)

| Comportamento | Como o cliente trata |
|---|---|
| Sem `codigoModalidadeContratacao` → **400** ("Required request parameter") | Uma consulta por modalidade configurada |
| `tamanhoPagina=51` → **400** ("Tamanho de página inválido") | Página fixa em 50 |
| Página além da última → **204 sem corpo** (não `data: []`) | 204 encerra a paginação |
| Itens/arquivos sem conteúdo → **204** | 204 vira lista vazia |
| **Itens, resultados e arquivos paginam, com 10 por página por padrão** (sem `pagina`/`tamanhoPagina` vêm só os 10 primeiros). Aceitam `tamanhoPagina` grande (1000 testado). Encontrado na Etapa 03: contratação com 11 itens na API e 10 na bronze | Paginação com 500 por página; para em página incompleta ou 204 |
| Orçamento sigiloso (`orcamentoSigiloso: true`) chega com `valorUnitarioEstimado: 0` e total `0` | Na silver vira **nulo** (desconhecido), nunca 0 |
| Filtro `uf` reduz muito o volume (1.576 → 35 num dia, pregão) | Ingestão por UF configurável (padrão CE) |
| Datas **sem fuso** (`"2025-09-01T00:00:47"`, horário de Brasília) | Bronze guarda como veio; a Etapa 03 aplica `America/Sao_Paulo` |
| Valores como **número JSON** (`200733.6`) | Bronze guarda como veio; a Etapa 03 converte para `Decimal` |
| Download do edital: `application/octet-stream` | Tipo detectado pelos bytes iniciais (`%PDF`, `PK`) |
| API de consulta rápida (~0,6 s), **API de detalhes às vezes lenta (~33 s por chamada)** | Timeout de 90 s, retry com backoff, intervalo mínimo entre chamadas |
| O PNCP adiciona campos novos com frequência (`emendaParlamentar`...) | Só os campos essenciais são validados; o bruto completo vai para a bronze |
| No resultado, `numeroItem` pode vir diferente do número do item consultado (ex.: `5392694`) | Resultados guardados pela chave do item consultado (`resultados["1"]`). O pipeline da silver (Etapa 03) usa essa chave e ignora o `numeroItem` de dentro do resultado |
| Vários resultados por item (registro de preços, `ordemClassificacaoSrp`) e resultados cancelados (`dataCancelamento`) | A silver guarda o 1º colocado não cancelado |
| `esferaId: "N"` em consórcios públicos (não documentado junto com F/E/M/D) | Aceito como "não se aplica" (migração 0003) |

## Códigos de modalidade (`modalidadeId`)

| Código | Modalidade |
|---|---|
| 1 | Leilão eletrônico |
| 2 | Diálogo competitivo |
| 3 | Concurso |
| 4 | Concorrência eletrônica |
| 5 | Concorrência presencial |
| 6 | **Pregão eletrônico** (padrão da ingestão) |
| 7 | Pregão presencial |
| 8 | **Dispensa de licitação** (padrão da ingestão) |
| 9 | Inexigibilidade |
| 10 | Manifestação de interesse |
| 11 | Pré-qualificação |
| 12 | Credenciamento |
| 13 | Leilão presencial |

## Como regravar as fixtures dos testes

```bash
make pncp-fixtures   # acessa a API real; rode só se o formato mudar
```

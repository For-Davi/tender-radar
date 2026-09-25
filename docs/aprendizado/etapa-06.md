# Etapa 06 — Frontend: dashboard

## O que foi construído (visão geral em 1 parágrafo)

Um frontend em **Next.js 16 + React 19 + TypeScript** (`frontend/`) com três telas:

| Tela | O que mostra |
|---|---|
| **Painel** (`/`) | 4 KPIs (contratações, valor estimado, órgãos, preços acima do p90), o gráfico de valor por mês e o de top fornecedores |
| **Contratações** (`/contratacoes`) | Filtros por UF, órgão, categoria, período e valor; ordenação; paginação. Os filtros ficam na URL |
| **Detalhe** (`/contratacoes/{id}`) | A contratação, os itens e o vencedor de cada item |

Toda tela tem estados de carregando, vazio e erro. Os tipos TypeScript são **gerados**
a partir do OpenAPI da API, e o CI falha se eles saírem de sincronia com o backend.

Os testes usam Vitest, Testing Library e MSW: **104 testes, 98% de cobertura**. A
imagem Docker é `standalone` e roda como usuário não-root. Com `make up`, o site fica em
`http://localhost:3000` com os dados reais.

## Como a lógica funciona (passo a passo, com trechos curtos de código)

```
backend (FastAPI) ──make openapi──> openapi.json ──openapi-typescript──> schema.d.ts (tipos)
                                                                              │
navegador ── página (server component) ── componente client ── hook (TanStack Query)
                                                                              │
                                                  openapi-fetch (tipado) ── GET http://localhost:8000/...
```

### 1. Os tipos vêm da API

`make openapi` roda `backend/scripts/exportar_openapi.py` (que chama
`create_app().openapi()`, sem subir servidor) e o `openapi-typescript`. O resultado
descreve cada rota:

```ts
ContratacaoResponse: {
  id: string;
  valor_total_estimado: string | null;   // dinheiro é texto; null = sigiloso
  data_publicacao: string;               // Format: date-time
  ...
}
```

O cliente usa esses tipos. `api.GET("/contratacoes", { params: { query: { uf: "CE" } } })`
só compila se a rota e o parâmetro existirem, e o `data` já vem tipado.

### 2. Uma chamada vira dado ou erro

```ts
export async function obter<T>(chamada: () => Promise<Resultado<T>>): Promise<T> {
  try { resultado = await chamada(); }
  catch { throw new ApiError(0, "Não foi possível conectar à API..."); }   // rede
  if (error !== undefined || !response.ok) throw new ApiError(status, problem.detail, problem);
  return data;
}
```

O `ApiError` guarda o problem+json do backend. Dois atalhos ajudam a tela a decidir o
que mostrar: `naoEncontrado` (404) e `indisponivel` (503, a gold não gerada).

### 3. Hooks do TanStack Query

```ts
export function useContratacoes(filtros: Filtros) {
  const query = paraParametros(filtros);
  return useQuery({
    queryKey: ["contratacoes", query],          // filtros diferentes = cache diferente
    queryFn: () => obter(() => api.GET("/contratacoes", { params: { query } })),
    placeholderData: keepPreviousData,          // a página atual fica na tela até a próxima chegar
  });
}
```

O componente só lê três coisas: `isPending` (carregando), `isError` (erro) e `data`.

### 4. Filtros na URL

- `ContratacoesPagina` lê `useSearchParams()` e chama `filtrosDaUrl`.
- A `ContratacoesView` recebe `filtros` e `onFiltrosChange`.
- Uma mudança vira `router.push("/contratacoes?uf=CE")`.
- `alterarFiltros` volta para a página 1 sempre que um filtro muda, porque a página 3 da
  busca antiga pode nem existir na nova.

```
/contratacoes?uf=CE&categoria=30&ordenar=-valor_total_estimado&pagina=2
        ⇅ filtrosDaUrl / filtrosParaUrl
{ uf: "CE", categoria: "30", ordenar: "-valor_total_estimado", pagina: 2, ... }
        ↓ paraParametros (campos vazios não vão)
GET /contratacoes?ordenar=-valor_total_estimado&pagina=2&tamanho_pagina=20&uf=CE&categoria=30
```

### 5. Formatação pt-BR (e a armadilha das datas)

```ts
formatarMoeda("1500.5000")                 // "R$ 1.500,50"
formatarMoeda(null, "Sigiloso")            // "Sigiloso"
formatarDataHora("2025-03-11T02:30:00Z")   // "10/03/2025, 23:30" (Brasília)
formatarMes("2026-09-01")                  // "set/2026"
```

**A armadilha das datas:** `new Date("2026-09-01")` é meia-noite **UTC**, que em
Brasília ainda é **31/08 às 21h**. Por isso as datas sem hora são formatadas pelo texto,
sem `Date`, e os testes rodam com `TZ=America/Sao_Paulo` para esse bug aparecer. Uma
mutação usando `new Date` derrubou 4 testes.

### 6. Server × client components

```tsx
// app/contratacoes/[id]/page.tsx: server component (roda no servidor Next)
export default async function Page({ params }: PageProps<"/contratacoes/[id]">) {
  const { id } = await params;                 // Next 16: params é uma Promise
  return <DetalheContratacao id={id} />;       // client component: busca e interage
}
```

A página de lista envolve o componente num `<Suspense>`, que o Next exige em volta de
quem usa `useSearchParams`.

## Decisões e alternativas (por que assim e não de outro jeito)

Resumo; o detalhe está no [ADR 0007](../adr/0007-frontend-nextjs.md).

| Decisão | Alternativa | Por quê |
|---|---|---|
| Node 24 via nvm | Manter o Node 18 | O 18 está fora de suporte; Next 16, Vitest 5 e jsdom exigem Node novo |
| TypeScript 5.9 | TypeScript 7 | O `typescript-eslint` e o `openapi-typescript` ainda não aceitam o 7 |
| Tipos gerados + verificação no CI | Tipos à mão | À mão, eles saem de sincronia com a API sem ninguém ver |
| Busca no cliente (TanStack Query) | Server components buscando | Telas interativas, testáveis com MSW, sem o Next precisar alcançar a API pela rede interna |
| Filtros na URL | Estado em memória | Link compartilhável; o "voltar" funciona |
| View recebe props | Ler a URL dentro da view | A view é testada sem simular o roteador |
| Formulário aplica ao enviar | Buscar a cada tecla | Uma requisição por letra seria desperdício |
| Navegador → API com CORS | Proxy pelo Next | O CORS já estava pronto; o proxy seria mais uma camada |
| Tabela acessível ao lado do gráfico | Só o gráfico | Um SVG não é lido por leitor de tela |

**Mudanças descobertas durante a etapa** (as três com teste):

1. **Os testes chamavam a API real.**
   - O `openapi-fetch` guardava o `fetch` da importação, e o MSW não interceptava.
   - O teste pegou pelo total (114 reais em vez de 2 falsos).
   - Correção: `fetch: (r) => globalThis.fetch(r)`.
2. **O tipo do `ProblemDetail` exigia campos que a API omite.** A causa era o padrão
   `defaultNonNullable` do `openapi-typescript`; agora ele é gerado com a opção desligada.
3. **O painel tinha uma rolagem horizontal invisível.**
   - Visto no navegador real: `<table class="sr-only">` não encolhe para 1 px.
   - O `sr-only` foi para uma `div` em volta da tabela.
   - Tem teste de regressão, validado contra o código antigo.
   - Na mesma inspeção, as barras do Recharts não apareciam (a animação não terminava);
     as animações foram desligadas.

## Conceitos novos (explicação didática de cada conceito/biblioteca usada)

### Next.js e React

- **Next.js (App Router):** cada pasta em `src/app/` é uma rota, e o arquivo `page.tsx`
  é a tela. O `layout.tsx` envolve todas as páginas, com a navegação e os providers.
- **Server × client components:**
  - *server components* (o padrão) rodam no servidor e mandam HTML pronto; não têm
    estado nem eventos;
  - `"use client"` marca um *client component*, que roda no navegador e pode usar
    `useState`, eventos e hooks.
  - Regra prática: a página é servidor, e o que interage é cliente.
- **`params` e `searchParams` como Promise (Next 15+):** a página faz
  `await params`. Os tipos `PageProps<"/rota">` são **gerados** pelo `next typegen` (o
  `typecheck` roda isso antes do `tsc`).
- **`NEXT_PUBLIC_*`:** variáveis com esse prefixo são **copiadas para o JavaScript do
  navegador no build**. Mudar o valor exige um build novo. Nunca coloque segredo nelas.
- **`output: "standalone"`:** o build gera um `server.js` com só os `node_modules`
  usados. A imagem final não roda `npm install`.

### Tipos e dados

- **openapi-typescript + openapi-fetch:**
  - o primeiro transforma o OpenAPI em tipos TypeScript;
  - o segundo é um `fetch` que usa esses tipos para conferir a rota, os parâmetros e a
    resposta em tempo de compilação.
- **TanStack Query:** cache de dados do servidor.
  - `queryKey` identifica o dado.
  - Ele deduplica requisições iguais, guarda o cache e refaz a busca quando o dado fica
    velho (`staleTime`).
  - Tenta de novo conforme a política `retry`.
  - Expõe `isPending`, `isError` e `data`.
- **Intl:** a API do JavaScript para formatar moeda, número e data por idioma e fuso,
  sem biblioteca extra.

### CSS e acessibilidade

- **Tailwind 4:** classes utilitárias (`rounded`, `px-3`...). A configuração do tema
  fica no CSS (`@theme`), e não há `tailwind.config.js`.
- **Acessibilidade básica:**
  - `label` em todo campo;
  - `role="status"` no carregando e `role="alert"` no erro;
  - `caption` e `scope` nas tabelas;
  - `aria-busy` enquanto atualiza;
  - link "pular para o conteúdo";
  - foco visível;
  - `lang="pt-BR"`, para o leitor de tela ler em português;
  - gráficos com uma tabela equivalente.
- **`sr-only`:** esconde da tela, mas não do leitor de tela. Numa `<table>` não
  funciona, porque tabela não aceita largura menor que o conteúdo.

### Testes

- **Vitest + Testing Library + MSW:**
  - o *Vitest* roda os testes num DOM simulado (jsdom);
  - a *Testing Library* procura elementos **como o usuário os vê** (`getByRole("button",
    { name: "Próxima" })`), e não por classes CSS;
  - o *MSW* intercepta o `fetch` e responde como a API responderia. Com
    `onUnhandledRequest: "error"`, nada escapa para a rede.
- **Contrato OpenAPI no CI:** regenera `openapi.json` e `schema.d.ts` e roda
  `git diff --exit-code`. Se a API mudou sem `make openapi`, o CI falha. Foi testado por
  mutação: mudar a descrição de um campo no backend derruba o passo.

## Testes (o que cada teste verifica e por que ele importa)

**104 testes, cobertura de 98% em `src/lib` e `src/components`** (o mínimo é 80%).

| Arquivo | O que prova |
|---|---|
| `lib/format.test.ts` | Moeda pt-BR (milhar, centavos, 8 casas → 2); nulo vira "Sigiloso" ou "—"; **02:30Z de 11/03 = 23:30 de 10/03** em Brasília; **o mês não volta um dia**; porcentagem; CNPJ com máscara (inclusive alfanumérico) |
| `lib/filtros.test.ts` | URL ↔ filtros nos dois sentidos; página e ordenação inválidas caem no padrão; **mudar um filtro volta para a página 1**; campos vazios não vão para a API |
| `lib/api/client.test.ts` | Dados tipados; parâmetros enviados; problem+json vira `ApiError` (404, 503); erro sem corpo; falha de rede; **política de retry** (repete rede e 5xx; não repete 4xx nem 503) |
| `ContratacoesView.test.tsx` | **Cada filtro altera a requisição** (UF, órgão, categoria), filtros combinados, ordenação e "limpar"; validação de datas e valores invertidos **sem chamar a API**; **paginação** (próxima, anterior, bordas desabilitadas, última página incompleta, página além da última); estados de carregando, vazio (com e sem filtro), erro da API e API fora do ar; categorias indisponíveis não impedem a busca |
| `ContratacoesPagina.test.tsx` | URL → requisição; mudar um filtro navega para a URL certa; limpar volta para `/contratacoes` |
| `DetalheContratacao.test.tsx` | Pede pelo id público; cabeçalho formatado; link do PNCP; itens com e sem vencedor, sigiloso e quantidades pt-BR; sem itens; 404 ("não encontrada", sem alerta); 422 |
| `Dashboard.test.tsx` | KPIs formatados; carregando (`aria-busy`); **gold 503: métricas avisam, KPIs da silver continuam**; API fora do ar; tabelas acessíveis dos gráficos; série vazia; nota "(1 mês)" na média móvel; soma de fornecedores entre órgãos; **regressão do `sr-only`** |
| `Paginacao.test.tsx`, `Navegacao.test.tsx` | Texto "Página X de Y"; botões nas bordas; some sem resultados; links principais |

**Mutações feitas** (cada uma derrubou testes):

| Mutação | Testes que falharam |
|---|---|
| `formatarMes` com `new Date` | 4 |
| Sem voltar para a página 1 | 4 |
| Tabela `sr-only` antiga | 1 |
| Campo mudado na API (contrato OpenAPI) | o `git diff` falha |

**Verificação no navegador real** (Chrome *headless*, com dados reais):

- o painel mostra 114 contratações, R$ 148,9 mi, 45 órgãos e 15 alertas;
- a lista filtrada por categoria 30 mostra 10 resultados ordenados por valor;
- o detalhe mostra o item com NCM;
- em tela estreita, os cards se reorganizam e a tabela rola dentro do contêiner.

## Como rodar e ver funcionando (comandos exatos)

```bash
make up                  # sobe tudo, inclusive o frontend: http://localhost:3000
```

Para desenvolver com recarga automática (a API precisa estar no ar, via `make up`):

```bash
nvm install 24           # uma vez; o frontend/.nvmrc seleciona a versão
make frontend-install    # npm ci
make frontend-dev        # http://localhost:3000 com recarga ao salvar
```

Qualidade:

```bash
make test-frontend       # só os testes do frontend
make lint-frontend       # prettier + eslint + tsc
make check               # backend + frontend, com cobertura
make openapi             # depois de mudar a API: regenera openapi.json e os tipos
```

Dentro de `frontend/`: `npm run test:watch` (testes ao salvar) e `npm run coverage`
(relatório HTML em `frontend/coverage/`).

## Erros comuns e como depurar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Unsupported engine` / erro estranho no `npm ci` | Node errado (18) | `nvm use` dentro de `frontend/` (lê o `.nvmrc`) |
| `Cannot find name 'PageProps'` | Tipos de rota não gerados | `npm run typecheck` (roda `next typegen` antes do `tsc`) |
| CI: "git diff --exit-code" no job frontend | A API mudou sem atualizar os tipos | `make openapi` e fazer commit de `openapi.json` e `schema.d.ts` |
| Tela: "Não foi possível conectar à API" | API fora do ar ou CORS | `make ps`; conferir `CORS_ORIGINS` (sem `/` no fim) |
| Painel: "As métricas ainda não foram geradas" | A gold não existe (503) | `make dbt` |
| Frontend aponta para a API errada | `NEXT_PUBLIC_API_URL` é fixado no build | Ajustar o `.env` e rodar `make up` (reconstrói) |
| Teste com `onUnhandledRequest` | Rota sem handler no MSW | Adicionar em `src/test/handlers.ts` ou com `server.use` no teste |
| Teste passa, mas "chama a API real" | O cliente guardou o `fetch` antigo | Manter `fetch: (r) => globalThis.fetch(r)` em `client.ts` |
| Data um dia antes | `new Date("AAAA-MM-DD")` em UTC | Usar `formatarData` / `formatarMes` |
| Gráfico vazio no teste | O jsdom não desenha SVG com tamanho | Testar pela tabela acessível, e não pelo SVG |

## Perguntas de revisão

1. Por que `new Date("2026-09-01")` mostra agosto para um usuário em Brasília? Como
   `formatarMes` evita isso, e por que os testes rodam com `TZ=America/Sao_Paulo`?
2. Qual a diferença entre um server component e um client component? Por que
   `DetalheContratacao` é client e a `page.tsx` do detalhe é server?
3. O que acontece, passo a passo, quando alguém muda um campo de resposta no FastAPI e
   esquece de rodar `make openapi`? Onde isso é pego?
4. Por que mudar a UF na página 3 deve levar à página 1? Qual teste garante isso?
5. Os testes do frontend chegaram a chamar a API real. Por quê, e como o teste
   percebeu?

# ADR 0007 — Frontend: Next.js com busca no cliente, tipos gerados do OpenAPI e filtros na URL

- **Status:** aceito
- **Data:** 2026-09-24
- **Etapa:** 06

## Contexto

A API da Etapa 05 precisava de uma interface para três usos:

- ver indicadores gerais (painel);
- buscar contratações com filtros;
- abrir o detalhe de cada uma.

Havia quatro restrições:

- **Ambiente:** o Node do WSL era o 18, fora de suporte desde abril de 2025. As versões
  atuais do Next (16), do Vitest (5), do jsdom e do ESLint exigem Node 20 ou 22+.
- **Compatibilidade:** o TypeScript 7 (o compilador reescrito em Go) ainda não é aceito
  pelo `typescript-eslint` (< 6.1) nem pelo `openapi-typescript` (^5).
- **Contrato:** o frontend não pode sair de sincronia com a API.
- **Testes:** nenhum teste pode chamar a API real (`CLAUDE.md`).

## Decisão

1. **Stack:**
   - Node 24 LTS (via nvm, fixado em `frontend/.nvmrc`);
   - Next.js 16 com App Router e React 19;
   - **TypeScript 5.9** strict, com `noUncheckedIndexedAccess`;
   - Tailwind 4, ESLint (`eslint-config-next` + `eslint-config-prettier`) e Prettier;
   - npm, com `package-lock.json` e versões exatas.
2. **Tipos gerados do OpenAPI.**
   - `backend/scripts/exportar_openapi.py` exporta o schema direto de `create_app()`,
     sem subir a API, para `frontend/openapi.json`.
   - O `openapi-typescript` gera `src/lib/api/schema.d.ts` a partir dele, com
     `--default-non-nullable false`: um campo com valor padrão pode faltar na resposta
     (o `ProblemDetail` omite os nulos).
   - Os dois arquivos são versionados.
   - O CI regenera os dois e falha se houver diferença.
3. **Cliente `openapi-fetch`.**
   - Cada chamada é tipada pela rota.
   - Erros viram um `ApiError` com o problem+json.
   - Uma falha de rede vira `status 0` com uma mensagem amigável.
   - O cliente busca o `fetch` global **a cada chamada**. Sem isso, o MSW não intercepta
     e os testes chamaram a API real; o bug foi pego e corrigido.
4. **Busca no cliente com TanStack Query.**
   - As páginas são server components finos, só com `params` e `searchParams`.
   - Os componentes interativos são client components.
   - A política de novas tentativas repete só falhas de rede e 5xx. Não repete 4xx nem
     503 (a gold só muda depois do `make dbt`).
5. **Filtros na URL.**
   - A view recebe `filtros` e `onFiltrosChange`; `ContratacoesPagina` liga isso a
     `useSearchParams` e `router.push`.
   - Mudar qualquer filtro volta para a página 1.
   - O formulário aplica os filtros ao enviar, e não a cada tecla.
6. **O navegador chama a API direto**, com `NEXT_PUBLIC_API_URL`, que é fixado no build.
   A API já libera o CORS para essa origem desde a Etapa 05.
7. **Formatação pt-BR** em `lib/format.ts`:
   - datas e horas sempre em `America/Sao_Paulo`;
   - datas sem hora nunca passam por `new Date()`;
   - os testes rodam com `TZ=America/Sao_Paulo`.
8. **Gráficos acessíveis.**
   - Cada gráfico do Recharts fica num `<figure>` com `<figcaption>`.
   - O SVG fica com `aria-hidden`, e uma tabela equivalente fica disponível para leitor
     de tela, dentro de uma `div.sr-only`.
   - As animações ficam desligadas.
9. **Entrega:**
   - imagem multi-stage `node:24-alpine`, com `output: "standalone"` e usuário `node`;
   - serviço `frontend` no Compose, com healthcheck;
   - telemetria do Next desligada;
   - `make lint`, `make test` e `make check` incluem o frontend (cobertura mínima de
     80%);
   - job `frontend` no CI e a imagem no `docker-build`.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter Node 18 e versões antigas | Fora de suporte (sem correções de segurança), e começaria o projeto já desatualizado |
| TypeScript 7 | O lint e o gerador de tipos ainda não o aceitam; migrar quando o ecossistema acompanhar |
| pnpm | Mais rápido, mas é mais uma ferramenta para um único pacote |
| Tipos escritos à mão | Sairiam de sincronia com a API sem ninguém perceber |
| Gerar os tipos da API no ar | Exigiria a stack rodando no build e no CI |
| Buscar os dados no servidor (RSC) | Bom para SEO, que não importa aqui; o servidor Next precisaria alcançar a API pela rede interna; e os testes com MSW ficariam mais difíceis |
| Proxy `/api` pelo Next (rewrites) | Evitaria o CORS, mas o destino também é fixado no build e seria mais uma camada |
| Estado dos filtros só em memória | O link não reproduz a busca e o "voltar" não desfaz o filtro |
| Mockar o `next/navigation` em todos os testes | A view recebe props; só o teste da página mocka o roteador (que é framework, não código nosso) |
| Tabela `sr-only` direto na `<table>` | Tabela não encolhe abaixo do conteúdo: gerou uma rolagem horizontal invisível (bug real, com teste) |
| Playwright para E2E | Fora do plano enxuto; a verificação no navegador foi manual, com Chrome *headless* |

## Consequências

- **Positivas:**
  - uma mudança na API que quebre o frontend falha no CI (contrato OpenAPI) ou no
    `tsc` (tipos);
  - 104 testes, com 98% de cobertura, rodando em cerca de 5 s sem navegador;
  - os bugs de fuso e de paginação são cobertos e validados por mutação.
- **Negativas:**
  - mudar a URL pública da API exige reconstruir a imagem (`NEXT_PUBLIC_*` entra no
    build);
  - o jsdom não calcula layout nem desenha gráficos: problemas visuais só aparecem no
    navegador.
- **A observar:**
  - com milhares de órgãos, o select de órgão (os 100 primeiros) precisa virar busca
    com autocompletar;
  - um teste E2E (Playwright) ou de regressão visual pegaria automaticamente o que o
    jsdom não vê.

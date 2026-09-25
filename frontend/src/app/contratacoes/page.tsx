import type { Metadata } from "next";
import { Suspense } from "react";

import { ContratacoesPagina } from "@/components/ContratacoesPagina";
import { Carregando } from "@/components/Estados";

export const metadata: Metadata = { title: "Contratações" };

// Server component fino: a parte interativa é client. O <Suspense> é exigido pelo
// Next em volta de quem usa useSearchParams (a query string só existe no navegador
// na hora do prerender).
export default function Page() {
  return (
    <Suspense fallback={<Carregando />}>
      <ContratacoesPagina />
    </Suspense>
  );
}

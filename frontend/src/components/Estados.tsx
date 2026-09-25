// Estados comuns a todas as telas: carregando, vazio e erro.
//
// Acessibilidade: `role="status"` é anunciado pelo leitor de tela sem interromper;
// `role="alert"` é anunciado na hora (erro precisa ser notado).
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/client";

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return (
    <p role="status" className="animate-pulse py-6 text-slate-500">
      {texto}
    </p>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return (
    <p className="rounded border border-dashed border-slate-300 bg-white p-6 text-center text-slate-600">
      {children}
    </p>
  );
}

/** Mensagem para o usuário a partir do erro da consulta. */
export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ApiError) {
    if (erro.indisponivel) {
      return "As métricas ainda não foram geradas. Rode make dbt e recarregue a página.";
    }
    return erro.message;
  }
  return "Erro inesperado. Tente novamente.";
}

export function Erro({
  erro,
  titulo = "Não foi possível carregar",
}: {
  erro: unknown;
  titulo?: string;
}) {
  return (
    <div role="alert" className="rounded border border-red-200 bg-red-50 p-4 text-red-800">
      <p className="font-semibold">{titulo}</p>
      <p className="text-sm">{mensagemDeErro(erro)}</p>
    </div>
  );
}

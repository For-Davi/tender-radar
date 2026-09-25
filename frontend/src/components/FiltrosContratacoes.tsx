"use client";

// Formulário de filtros. Os campos têm estado LOCAL enquanto o usuário digita; a busca
// só acontece ao enviar ("Filtrar"), e não a cada tecla (uma requisição por letra
// digitada no valor mínimo seria desperdício).
import { useState, type FormEvent } from "react";

import { useCategorias, useOrgaos } from "@/lib/api/queries";
import { FILTROS_VAZIOS, type Filtros } from "@/lib/filtros";

const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
  "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]; // prettier-ignore

type CamposFormulario = Omit<Filtros, "ordenar" | "pagina">;

interface Props {
  filtros: Filtros;
  onAplicar: (campos: CamposFormulario) => void;
}

const campo = "flex flex-col gap-1 text-sm";
const entrada = "rounded border border-slate-300 bg-white px-2 py-1";

export function FiltrosContratacoes({ filtros, onAplicar }: Props) {
  const [valores, setValores] = useState<CamposFormulario>(() => ({
    uf: filtros.uf,
    orgao: filtros.orgao,
    categoria: filtros.categoria,
    data_inicio: filtros.data_inicio,
    data_fim: filtros.data_fim,
    valor_min: filtros.valor_min,
    valor_max: filtros.valor_max,
  }));
  const [invalido, setInvalido] = useState<string | null>(null);
  const orgaos = useOrgaos();
  const categorias = useCategorias();

  const mudar = (nome: keyof CamposFormulario) => (evento: { target: { value: string } }) =>
    setValores((atual) => ({ ...atual, [nome]: evento.target.value }));

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    // a API também valida (422), mas avisar antes poupa uma ida ao servidor
    if (valores.data_inicio && valores.data_fim && valores.data_inicio > valores.data_fim) {
      setInvalido("A data inicial não pode ser depois da data final.");
      return;
    }
    if (
      valores.valor_min &&
      valores.valor_max &&
      Number(valores.valor_min) > Number(valores.valor_max)
    ) {
      setInvalido("O valor mínimo não pode ser maior que o máximo.");
      return;
    }
    setInvalido(null);
    onAplicar(valores);
  }

  function limpar() {
    const { ordenar, pagina, ...vazios } = FILTROS_VAZIOS;
    setValores(vazios);
    setInvalido(null);
    onAplicar(vazios);
  }

  // só categorias com capítulo NCM são filtráveis ("sem classificação" não tem código)
  const filtraveis = (categorias.data ?? []).filter((c) => c.ncm_capitulo !== null);

  return (
    <form
      onSubmit={enviar}
      aria-label="Filtros"
      className="grid grid-cols-2 gap-3 rounded border border-slate-200 bg-white p-4 md:grid-cols-4"
    >
      <label className={campo}>
        UF
        <select value={valores.uf} onChange={mudar("uf")} className={entrada}>
          <option value="">Todas</option>
          {UFS.map((uf) => (
            <option key={uf}>{uf}</option>
          ))}
        </select>
      </label>

      <label className={`${campo} col-span-2`}>
        Órgão
        <select
          value={valores.orgao}
          onChange={mudar("orgao")}
          disabled={orgaos.isPending}
          className={entrada}
        >
          <option value="">{orgaos.isPending ? "Carregando órgãos…" : "Todos"}</option>
          {orgaos.data?.itens.map((o) => (
            <option key={o.cnpj} value={o.cnpj}>
              {o.razao_social}
            </option>
          ))}
        </select>
      </label>

      <label className={campo}>
        Categoria
        <select
          value={valores.categoria}
          onChange={mudar("categoria")}
          disabled={!categorias.isSuccess}
          className={entrada}
        >
          <option value="">{categorias.isError ? "Indisponível" : "Todas"}</option>
          {filtraveis.map((c) => (
            <option key={`${c.material_ou_servico}-${c.ncm_capitulo}`} value={c.ncm_capitulo ?? ""}>
              {c.nome}
            </option>
          ))}
        </select>
      </label>

      <label className={campo}>
        Publicada a partir de
        <input
          type="date"
          value={valores.data_inicio}
          onChange={mudar("data_inicio")}
          className={entrada}
        />
      </label>
      <label className={campo}>
        Publicada até
        <input
          type="date"
          value={valores.data_fim}
          onChange={mudar("data_fim")}
          className={entrada}
        />
      </label>
      <label className={campo}>
        Valor mínimo (R$)
        <input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          value={valores.valor_min}
          onChange={mudar("valor_min")}
          className={entrada}
        />
      </label>
      <label className={campo}>
        Valor máximo (R$)
        <input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          value={valores.valor_max}
          onChange={mudar("valor_max")}
          className={entrada}
        />
      </label>

      {invalido && (
        <p role="alert" className="col-span-full text-sm text-alerta">
          {invalido}
        </p>
      )}

      <div className="col-span-full flex gap-2">
        <button type="submit" className="rounded bg-marca px-4 py-1.5 font-medium text-white">
          Filtrar
        </button>
        <button
          type="button"
          onClick={limpar}
          className="rounded border border-slate-300 px-4 py-1.5"
        >
          Limpar filtros
        </button>
      </div>
    </form>
  );
}

"""Fakes em memória dos ports de leitura (`ContratacaoQueries`, `OrgaoQueries`...).

Eles NÃO filtram nem ordenam: guardam os argumentos recebidos (`chamadas`) para o
teste conferir que a API traduziu a query string no filtro certo. Filtrar de
verdade é trabalho do SQL, testado contra o Postgres real em `tests/integration/`.
Paginar eles paginam (fatiar uma lista), para o envelope de resposta ser realista.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)
from radar.ports.consultas import (
    ContratacaoDetalhe,
    ContratacaoResumo,
    FiltroContratacoes,
    FornecedorRef,
    ItemDetalhe,
    Ordenacao,
    OrgaoRef,
    OrgaoResumo,
    Pagina,
    PaginaPedido,
)
from radar.ports.metricas import (
    AnaliticoIndisponivelError,
    Categoria,
    PrecoAcimaP90,
    PrecoCategoriaMensal,
    RankingFornecedor,
    ValorMensal,
)

CNPJ_ORGAO = "07954480000179"

# Any: os overrides são repassados como kwargs e cada read model tem seus próprios tipos


def _paginar[T](itens: Sequence[T], pedido: PaginaPedido) -> Pagina[T]:
    fatia = itens[pedido.offset : pedido.offset + pedido.tamanho]
    return Pagina(list(fatia), len(itens), pedido)


def make_resumo(sequencial: int = 1, **overrides: Any) -> ContratacaoResumo:
    fields: dict[str, Any] = {
        "numero_controle_pncp": f"{CNPJ_ORGAO}-1-{sequencial:06d}/2025",
        "orgao": OrgaoRef(cnpj=CNPJ_ORGAO, razao_social="Estado do Ceará"),
        "modalidade": Modalidade.PREGAO_ELETRONICO,
        "situacao": SituacaoContratacao.DIVULGADA,
        "objeto": f"Objeto {sequencial}",
        "valor_total_estimado": Decimal("1500.5000"),
        "data_publicacao": datetime(2025, 3, 10, 15, 0, tzinfo=UTC),
        "uf": "CE",
        "municipio": "Fortaleza",
        "total_itens": 2,
    }
    return ContratacaoResumo(**(fields | overrides))


def make_item_detalhe(numero_item: int = 1, **overrides: Any) -> ItemDetalhe:
    fields: dict[str, Any] = {
        "numero_item": numero_item,
        "descricao": "Dipirona 500mg",
        "material_ou_servico": MaterialOuServico.MATERIAL,
        "ncm_nbs": "30049099",
        "quantidade": Decimal("10.0000"),
        "unidade_medida": "Unidade",
        "valor_unitario_estimado": Decimal("0.3333"),
        "vencedor": None,
        "valor_unitario_homologado": None,
    }
    return ItemDetalhe(**(fields | overrides))


VENCEDOR = FornecedorRef(
    documento="12ABC34501DE35", nome="Farmácia Exemplo Ltda", tipo_pessoa=TipoPessoa.JURIDICA
)


@dataclass
class FakeContratacaoQueries:
    contratacoes: list[ContratacaoDetalhe] = field(default_factory=list)
    chamadas: list[tuple[FiltroContratacoes, Ordenacao, PaginaPedido]] = field(default_factory=list)

    def listar(
        self, filtro: FiltroContratacoes, ordenacao: Ordenacao, pedido: PaginaPedido
    ) -> Pagina[ContratacaoResumo]:
        self.chamadas.append((filtro, ordenacao, pedido))
        return _paginar([c.resumo for c in self.contratacoes], pedido)

    def detalhar(self, numero_controle_pncp: str) -> ContratacaoDetalhe | None:
        return next(
            (c for c in self.contratacoes if c.resumo.numero_controle_pncp == numero_controle_pncp),
            None,
        )


@dataclass
class FakeOrgaoQueries:
    orgaos: list[OrgaoResumo] = field(default_factory=list)
    chamadas: list[tuple[str | None, PaginaPedido]] = field(default_factory=list)

    def listar(self, uf: str | None, pedido: PaginaPedido) -> Pagina[OrgaoResumo]:
        self.chamadas.append((uf, pedido))
        return _paginar(self.orgaos, pedido)


def make_orgao_resumo(n: int = 1) -> OrgaoResumo:
    return OrgaoResumo(
        cnpj=f"{n:014d}",
        razao_social=f"Órgão {n}",
        esfera=Esfera.ESTADUAL,
        poder=Poder.EXECUTIVO,
        total_contratacoes=n,
    )


CATEGORIA_30 = Categoria(
    material_ou_servico=MaterialOuServico.MATERIAL,
    ncm_capitulo="30",
    nome="30 - Produtos farmacêuticos",
)
SEM_CLASSIFICACAO = Categoria(
    material_ou_servico=MaterialOuServico.MATERIAL,
    ncm_capitulo=None,
    nome="Material sem classificação",
)


@dataclass
class FakeMetricasQueries:
    """Métricas prontas. `indisponivel=True` simula a gold ainda não gerada."""

    indisponivel: bool = False
    chamadas: list[tuple[str, object]] = field(default_factory=list)
    alertas: list[PrecoAcimaP90] = field(default_factory=list)

    def _registrar(self, metodo: str, argumento: object = None) -> None:
        self.chamadas.append((metodo, argumento))
        if self.indisponivel:
            raise AnaliticoIndisponivelError('relation "gold.dim_categoria" does not exist')

    def categorias(self) -> Sequence[Categoria]:
        self._registrar("categorias")
        return [SEM_CLASSIFICACAO, CATEGORIA_30]

    def valor_mensal(self) -> Sequence[ValorMensal]:
        self._registrar("valor_mensal")
        return [
            ValorMensal(
                mes=date(2026, 1, 1),
                contratacoes=1,
                itens=2,
                valor_total_estimado=Decimal("300.0000"),
                media_movel_3m=Decimal("300.00"),
                meses_na_media=1,
            ),
            ValorMensal(
                mes=date(2026, 2, 1),
                contratacoes=0,
                itens=0,
                valor_total_estimado=Decimal("0"),
                media_movel_3m=Decimal("150.00"),
                meses_na_media=2,
            ),
        ]

    def preco_categoria(self, ncm_capitulo: str | None) -> Sequence[PrecoCategoriaMensal]:
        self._registrar("preco_categoria", ncm_capitulo)
        return [
            PrecoCategoriaMensal(
                categoria=CATEGORIA_30,
                unidade="UNIDADE",
                mes=date(2026, 2, 1),
                itens=1,
                preco_medio=Decimal("16.5000"),
                preco_mediano=Decimal("16.5000"),
                preco_mediano_mes_anterior=Decimal("15.0000"),
                variacao_percentual=Decimal("10.00"),
            )
        ]

    def ranking_fornecedores(self, orgao_cnpj: str | None) -> Sequence[RankingFornecedor]:
        self._registrar("ranking_fornecedores", orgao_cnpj)
        return [
            RankingFornecedor(
                orgao_cnpj=CNPJ_ORGAO,
                orgao_razao_social="Estado do Ceará",
                fornecedor_documento="12ABC34501DE35",
                fornecedor_nome="Farmácia Exemplo Ltda",
                itens_vencidos=2,
                valor_total_homologado=Decimal("1000.0000"),
                ranking=1,
                participacao_percentual=Decimal("40.00"),
            )
        ]

    def precos_acima_p90(self, pedido: PaginaPedido) -> Pagina[PrecoAcimaP90]:
        self._registrar("precos_acima_p90", pedido)
        return _paginar(self.alertas, pedido)


def make_alerta(numero_item: int = 1) -> PrecoAcimaP90:
    return PrecoAcimaP90(
        numero_controle_pncp=f"{CNPJ_ORGAO}-1-000001/2025",
        numero_item=numero_item,
        orgao_razao_social="Estado do Ceará",
        categoria_nome="30 - Produtos farmacêuticos",
        unidade="UNIDADE",
        data_publicacao=date(2025, 3, 10),
        valor_unitario_estimado=Decimal("50.0000"),
        percentil_preco=Decimal("1.0000"),
        itens_comparaveis=5,
    )

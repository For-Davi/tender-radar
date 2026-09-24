"""Transforma uma versão da bronze em entidades limpas da silver, ou em rejeições.

Função pura (sem I/O): recebe o JSON bruto e devolve o resultado. Toda a regra de
qualidade de dados está aqui; o pipeline (`bronze_to_silver.py`) só lê, grava e conta.

Duas camadas de validação:
1. Pydantic (`schemas_bronze.py`): formato e completude, com o caminho do campo;
2. entidades do domínio: regras de negócio (quantidade > 0, UF válida, CNPJ...).

Unidade de rejeição:
- problema nos dados da contratação -> a contratação inteira é rejeitada;
- problema num item (ou no resultado dele) -> só o item é rejeitado.
"""

from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError

from radar.domain.entities import Contratacao, Fornecedor, ItemContratacao, Orgao
from radar.domain.errors import DomainError, InvalidValueError
from radar.domain.value_objects import Cnpj, Dinheiro
from radar.pipelines.schemas_bronze import (
    ContratacaoBronze,
    ItemBronze,
    PayloadBronze,
    ResultadoBronze,
)
from radar.ports.bronze import BronzeVersion
from radar.ports.contratacoes_source import JsonDict
from radar.ports.silver import MotivoRejeicao, Problema, Rejeicao

# divergência tolerada entre o total da contratação e a soma dos itens (arredondamentos)
TOLERANCIA_CONSISTENCIA = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ContratacaoLimpa:
    orgao: Orgao
    fornecedores: tuple[Fornecedor, ...]
    contratacao: Contratacao
    # total da contratação diverge da soma dos itens: sinalizado, mas gravado
    inconsistente: bool


@dataclass(frozen=True, slots=True)
class Transformacao:
    limpa: ContratacaoLimpa | None  # None = contratação rejeitada
    rejeicoes: tuple[Rejeicao, ...]


class _RejeicaoError(Exception):
    """Uso interno: interrompe o processamento de um item/contratação com o motivo."""

    def __init__(self, motivo: MotivoRejeicao, problemas: list[Problema]) -> None:
        super().__init__(motivo.value)
        self.motivo = motivo
        self.problemas = problemas


def transformar(versao: BronzeVersion) -> Transformacao:
    return _Transformador(versao).executar()


# ------------------------------------------------------------------ helpers de erro


def _caminho(prefixo: str, loc: tuple[int | str, ...]) -> str:
    """("orgaoEntidade", "cnpj") -> "contratacao.orgaoEntidade.cnpj"; índices viram [n]."""
    caminho = prefixo
    for parte in loc:
        if isinstance(parte, int):
            caminho += f"[{parte}]"
        elif caminho:
            caminho += f".{parte}"
        else:
            caminho = parte
    return caminho


def _problemas_pydantic(exc: ValidationError, prefixo: str) -> list[Problema]:
    return [Problema(_caminho(prefixo, error["loc"]), error["msg"]) for error in exc.errors()]


def _motivo_do_dominio(exc: DomainError) -> MotivoRejeicao:
    # InvalidValueError = formato (CNPJ, UF...); o resto = regra de negócio
    if isinstance(exc, InvalidValueError):
        return MotivoRejeicao.CAMPO_INVALIDO
    return MotivoRejeicao.REGRA_NEGOCIO


def _dominio(exc: DomainError, campo: str, motivo: MotivoRejeicao | None = None) -> _RejeicaoError:
    return _RejeicaoError(motivo or _motivo_do_dominio(exc), [Problema(campo, str(exc))])


def _numero_item_bruto(bruto: JsonDict) -> int | None:
    """O número do item, se legível, para registrar a rejeição mesmo com o item inválido."""
    numero = bruto.get("numeroItem")
    # bool é int em Python: True não é um número de item
    return numero if isinstance(numero, int) and not isinstance(numero, bool) else None


def _ordem_resultado(resultado: ResultadoBronze) -> tuple[bool, int, int]:
    """Critério do vencedor: menor ordem de classificação SRP; sem ordem vai por último;
    empate desempata pelo sequencial do resultado."""
    ordem = resultado.ordem_classificacao_srp
    return (ordem is None, ordem or 0, resultado.sequencial_resultado)


def _diverge(total: Dinheiro | None, soma_itens: Dinheiro | None) -> bool:
    if total is None or soma_itens is None or total.valor == 0:
        return False
    return abs(total.valor - soma_itens.valor) / total.valor > TOLERANCIA_CONSISTENCIA


# ------------------------------------------------------------------ transformação


class _Transformador:
    """Guarda o estado de uma transformação (itens vistos, rejeições acumuladas)."""

    def __init__(self, versao: BronzeVersion) -> None:
        self._versao = versao
        self._rejeicoes: list[Rejeicao] = []
        self._numeros_vistos: set[int] = set()
        self._fornecedores: dict[str, Fornecedor] = {}

    def executar(self) -> Transformacao:
        try:
            payload, cabecalho = self._ler_contratacao()
            itens = self._ler_itens(payload)
            limpa = self._montar(cabecalho, itens)
        except _RejeicaoError as exc:
            # contratação rejeitada: as rejeições de itens não importam mais
            return Transformacao(None, (self._rejeicao(exc),))
        return Transformacao(limpa, tuple(self._rejeicoes))

    def _rejeicao(self, exc: _RejeicaoError, numero_item: int | None = None) -> Rejeicao:
        return Rejeicao(
            numero_controle_pncp=self._versao.numero_controle_pncp,
            bronze_hash=self._versao.hash,
            motivo=exc.motivo,
            problemas=tuple(exc.problemas),
            numero_item=numero_item,
        )

    # ---------------------------------------------------------- contratação

    def _ler_contratacao(self) -> tuple[PayloadBronze, ContratacaoBronze]:
        try:
            payload = PayloadBronze.model_validate(self._versao.payload)
        except ValidationError as exc:
            raise _RejeicaoError(
                MotivoRejeicao.CAMPO_INVALIDO, _problemas_pydantic(exc, "")
            ) from exc
        try:
            cabecalho = ContratacaoBronze.model_validate(payload.contratacao)
        except ValidationError as exc:
            raise _RejeicaoError(
                MotivoRejeicao.CAMPO_INVALIDO, _problemas_pydantic(exc, "contratacao")
            ) from exc
        return payload, cabecalho

    def _montar(
        self, cabecalho: ContratacaoBronze, itens: list[ItemContratacao]
    ) -> ContratacaoLimpa:
        try:
            cnpj = Cnpj(cabecalho.orgao.cnpj)
            orgao = Orgao(
                cnpj=cnpj,
                razao_social=cabecalho.orgao.razao_social,
                esfera=cabecalho.orgao.esfera,
                poder=cabecalho.orgao.poder,
            )
            contratacao = Contratacao(
                numero_controle_pncp=cabecalho.numero_controle_pncp,
                orgao_cnpj=cnpj,
                modalidade=cabecalho.modalidade,
                situacao=cabecalho.situacao,
                objeto=cabecalho.objeto,
                valor_total_estimado=self._valor_total(cabecalho, itens),
                data_publicacao=cabecalho.data_publicacao,
                uf=cabecalho.unidade.uf.upper(),
                municipio=cabecalho.unidade.municipio,
                itens=itens,
            )
        except DomainError as exc:
            raise _dominio(exc, "contratacao") from exc
        return ContratacaoLimpa(
            orgao=orgao,
            fornecedores=tuple(self._fornecedores.values()),
            contratacao=contratacao,
            inconsistente=_diverge(
                contratacao.valor_total_estimado, contratacao.valor_total_itens()
            ),
        )

    @staticmethod
    def _valor_total(cabecalho: ContratacaoBronze, itens: list[ItemContratacao]) -> Dinheiro | None:
        valor = cabecalho.valor_total_estimado
        if valor is None:
            return None
        # total 0 com todos os itens sigilosos: o total também é sigiloso, não zero
        if valor == 0 and itens and all(i.valor_unitario_estimado is None for i in itens):
            return None
        return Dinheiro(valor)

    # ---------------------------------------------------------- itens

    def _ler_itens(self, payload: PayloadBronze) -> list[ItemContratacao]:
        itens: list[ItemContratacao] = []
        for posicao, bruto in enumerate(payload.itens):
            try:
                itens.append(self._ler_item(payload, posicao, bruto))
            except _RejeicaoError as exc:
                # se o item não tem número legível, registra com numero_item=None
                self._rejeicoes.append(self._rejeicao(exc, _numero_item_bruto(bruto)))
        return itens

    def _ler_item(self, payload: PayloadBronze, posicao: int, bruto: JsonDict) -> ItemContratacao:
        campo = f"itens[{posicao}]"
        try:
            item = ItemBronze.model_validate(bruto)
        except ValidationError as exc:
            raise _RejeicaoError(
                MotivoRejeicao.CAMPO_INVALIDO, _problemas_pydantic(exc, campo)
            ) from exc
        if item.numero_item in self._numeros_vistos:
            raise _RejeicaoError(
                MotivoRejeicao.ITEM_DUPLICADO,
                [Problema(f"{campo}.numeroItem", f"número de item repetido: {item.numero_item}")],
            )
        self._numeros_vistos.add(item.numero_item)

        fornecedor, homologado = self._ler_resultado(payload, item.numero_item)
        try:
            limpo = ItemContratacao(
                numero_item=item.numero_item,
                descricao=item.descricao,
                material_ou_servico=item.material_ou_servico,
                categoria=item.categoria,
                quantidade=item.quantidade,
                unidade_medida=item.unidade_medida,
                valor_unitario_estimado=self._valor_estimado(item),
                fornecedor_documento=fornecedor.documento if fornecedor else None,
                valor_unitario_homologado=homologado,
                ncm_nbs=item.ncm_nbs,
            )
        except DomainError as exc:
            raise _dominio(exc, campo) from exc
        if fornecedor is not None:
            self._fornecedores.setdefault(fornecedor.documento, fornecedor)
        return limpo

    @staticmethod
    def _valor_estimado(item: ItemBronze) -> Dinheiro | None:
        # sigiloso: o PNCP manda 0, mas o valor é desconhecido
        if item.orcamento_sigiloso or item.valor_unitario_estimado is None:
            return None
        return Dinheiro(item.valor_unitario_estimado)

    # ---------------------------------------------------------- resultado do item

    def _ler_resultado(
        self, payload: PayloadBronze, numero_item: int
    ) -> tuple[Fornecedor | None, Dinheiro | None]:
        """Escolhe o vencedor do item entre os resultados não cancelados."""
        prefixo = f"resultados.{numero_item}"
        validos: list[tuple[int, ResultadoBronze]] = []
        for posicao, bruto in enumerate(payload.resultados.get(str(numero_item), [])):
            try:
                resultado = ResultadoBronze.model_validate(bruto)
            except ValidationError as exc:
                raise _RejeicaoError(
                    MotivoRejeicao.RESULTADO_INVALIDO,
                    _problemas_pydantic(exc, f"{prefixo}[{posicao}]"),
                ) from exc
            if resultado.data_cancelamento is None:
                validos.append((posicao, resultado))
        if not validos:
            return None, None

        posicao, vencedor = min(validos, key=lambda par: _ordem_resultado(par[1]))
        try:
            fornecedor = Fornecedor(
                tipo_pessoa=vencedor.tipo_pessoa,
                documento=vencedor.ni_fornecedor,
                nome=vencedor.nome_fornecedor,
            )
        except DomainError as exc:
            raise _dominio(exc, f"{prefixo}[{posicao}]", MotivoRejeicao.RESULTADO_INVALIDO) from exc
        return fornecedor, Dinheiro(vencedor.valor_unitario_homologado)

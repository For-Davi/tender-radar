"""Todo código do PNCP conhecido pelo domínio precisa de um nome na API.

Se alguém somar um membro a um enum (como aconteceu com a esfera "N"), sem somar o
nome aqui, a API daria KeyError (500) na primeira contratação com o código novo.
Este teste pega isso antes.
"""

from enum import Enum

import pytest

from radar.api import rotulos
from radar.domain.enums import (
    Esfera,
    MaterialOuServico,
    Modalidade,
    Poder,
    SituacaoContratacao,
    TipoPessoa,
)


@pytest.mark.parametrize(
    ("enum", "nomes"),
    [
        (Modalidade, rotulos.MODALIDADE),
        (SituacaoContratacao, rotulos.SITUACAO),
        (Esfera, rotulos.ESFERA),
        (Poder, rotulos.PODER),
        (TipoPessoa, rotulos.TIPO_PESSOA),
        (MaterialOuServico, rotulos.MATERIAL_OU_SERVICO),
    ],
)
def test_every_enum_member_has_a_label(enum: type[Enum], nomes: dict[Enum, str]) -> None:
    assert set(nomes) == set(enum)
    assert all(nome.strip() for nome in nomes.values())

import json
from datetime import date
from pathlib import Path

from sync.admission import classificar
from sync.config import carregar_config

HOJE = date(2026, 8, 27)


def _cfg():
    return carregar_config(Path("config.json")).admissao


def _detalhe(**extras) -> dict:
    base = {
        "id": 1,
        "adult": False,
        "runtime": 120,
        "vote_count": 0,
        "popularity": 0.0,
        "release_date": "1999-03-31",
    }
    return {**base, **extras}


def test_config_carrega_os_pesos_do_motor():
    motor = carregar_config(Path("config.json")).motor
    assert motor.pesos["keyword"] == 0.40
    assert sum(motor.pesos.values()) == 1.0


def test_filme_com_muitos_votos_entra_no_acervo():
    assert classificar(_detalhe(vote_count=50), HOJE, _cfg()) == "acervo"


def test_filme_com_poucos_votos_e_antigo_fica_de_fora():
    assert classificar(_detalhe(vote_count=49), HOJE, _cfg()) is None


def test_lancamento_recente_com_poucos_votos_entra_como_recente():
    recente = _detalhe(vote_count=5, release_date="2026-08-01")
    assert classificar(recente, HOJE, _cfg()) == "recente"


def test_lancamento_recente_entra_por_popularidade_sem_votos():
    recente = _detalhe(vote_count=0, popularity=25.0, release_date="2026-08-01")
    assert classificar(recente, HOJE, _cfg()) == "recente"


def test_lancamento_recente_sem_votos_nem_popularidade_fica_de_fora():
    recente = _detalhe(vote_count=0, popularity=0.5, release_date="2026-08-01")
    assert classificar(recente, HOJE, _cfg()) is None


def test_curta_metragem_nunca_entra():
    curta = _detalhe(vote_count=9999, runtime=40)
    assert classificar(curta, HOJE, _cfg()) is None


def test_adulto_nunca_entra():
    assert classificar(_detalhe(vote_count=9999, adult=True), HOJE, _cfg()) is None


def test_sem_data_de_lancamento_so_pode_entrar_pelo_acervo():
    assert classificar(_detalhe(vote_count=50, release_date=""), HOJE, _cfg()) == "acervo"
    assert classificar(_detalhe(vote_count=5, release_date=""), HOJE, _cfg()) is None


def test_acervo_tem_prioridade_sobre_recente():
    # Um lançamento que já explodiu de votos é acervo, não recente: ele não
    # deve expirar em 18 meses.
    campeao = _detalhe(vote_count=5000, release_date="2026-08-01")
    assert classificar(campeao, HOJE, _cfg()) == "acervo"


def test_runtime_ausente_e_tratado_como_zero():
    assert classificar(_detalhe(vote_count=9999, runtime=None), HOJE, _cfg()) is None

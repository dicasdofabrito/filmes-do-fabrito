import json
from datetime import date
from pathlib import Path

from sync.theatrical import apenas_no_cinema

HOJE = date(2026, 8, 27)
FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def test_em_cartaz_sem_lancamento_domestico_e_apenas_cinema():
    assert apenas_no_cinema(_fixture("release_dates_em_cartaz.json"), HOJE) is True


def test_com_lancamento_digital_deixa_de_ser_apenas_cinema():
    assert apenas_no_cinema(_fixture("release_dates_ja_lancado.json"), HOJE) is False


def test_sem_estreia_no_brasil_nao_e_apenas_cinema():
    dados = {"results": [{"iso_3166_1": "US", "release_dates": [{"type": 3, "release_date": "2026-08-01T00:00:00.000Z"}]}]}
    assert apenas_no_cinema(dados, HOJE) is False


def test_estreia_futura_ainda_nao_conta_como_em_cartaz():
    dados = {"results": [{"iso_3166_1": "BR", "release_dates": [{"type": 3, "release_date": "2026-12-01T00:00:00.000Z"}]}]}
    assert apenas_no_cinema(dados, HOJE) is False


def test_digital_marcado_para_o_futuro_nao_tira_do_cinema():
    # Data de digital anunciada mas ainda não chegada: continua só no cinema.
    dados = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "2026-08-01T00:00:00.000Z"},
                    {"type": 4, "release_date": "2026-11-01T00:00:00.000Z"},
                ],
            }
        ]
    }
    assert apenas_no_cinema(dados, HOJE) is True


def test_resposta_vazia_nao_quebra():
    assert apenas_no_cinema({}, HOJE) is False
    assert apenas_no_cinema({"results": []}, HOJE) is False


def test_lancamento_domestico_em_outro_pais_tira_do_cinema():
    # Caso real encontrado na carga inicial: TMDB registra estreia em sala
    # no Brasil, mas nunca cadastra data de digital/físico especificamente
    # para o Brasil -- mesmo em clássicos disponíveis há décadas. Se saiu
    # em digital ou físico em QUALQUER país, o Fabio consegue acessar.
    dados = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "1925-01-01T00:00:00.000Z"}
                ],
            },
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 5, "release_date": "1980-01-01T00:00:00.000Z"}
                ],
            },
        ]
    }
    assert apenas_no_cinema(dados, HOJE) is False


def test_estreia_muito_antiga_sem_lancamento_domestico_nao_e_apenas_cinema():
    # Caso real: Ben-Hur (1925) estreou em dezenas de países mas o TMDB nunca
    # registrou uma data de lançamento doméstico em NENHUM deles -- lacuna de
    # catalogação do TMDB para filmes antigos, não disponibilidade real.
    dados = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "1925-12-25T00:00:00.000Z"}
                ],
            },
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 3, "release_date": "1925-12-30T00:00:00.000Z"}
                ],
            },
        ]
    }
    assert apenas_no_cinema(dados, HOJE) is False


def test_estreia_recente_sem_lancamento_domestico_continua_apenas_cinema():
    # Um lançamento de fato recente, dentro da janela de tolerância, sem
    # registro de doméstico em lugar nenhum: continua só no cinema.
    dados = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "2026-06-01T00:00:00.000Z"}
                ],
            }
        ]
    }
    assert apenas_no_cinema(dados, HOJE) is True


def test_lancamento_domestico_futuro_em_outro_pais_nao_tira_do_cinema():
    dados = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "2026-08-01T00:00:00.000Z"}
                ],
            },
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"type": 4, "release_date": "2026-12-01T00:00:00.000Z"}
                ],
            },
        ]
    }
    assert apenas_no_cinema(dados, HOJE) is True

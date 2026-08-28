import json
import math
from pathlib import Path

import pytest

from sync.catalog import Movie
from sync.profile import (
    Entry,
    Profile,
    construir_gosto,
    features_of,
    gosto_de_um_filme,
    ler_perfil,
)


def _filme(id_: int, *, keywords=(), genres=(), directors=(), year=2000) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=100,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=7.0, vote_count=100,
        directors=tuple(directors), cast=(), language="en",
        track="acervo", theatrical=False, added="2026-08-27",
    )


def test_ler_perfil_separa_curtidos_rejeitados_e_watchlist(tmp_path: Path):
    caminho = tmp_path / "profile.json"
    caminho.write_text(
        json.dumps(
            {
                "movies": {
                    "1": {"seen": True, "rating": 1, "at": "2026-08-20"},
                    "2": {"seen": True, "rating": -1, "at": "2026-08-21"},
                    "3": {"seen": False, "want": True, "at": "2026-08-22"},
                }
            }
        ),
        encoding="utf-8",
    )
    perfil = ler_perfil(caminho)

    assert perfil.liked_ids() == {1}
    assert perfil.disliked_ids() == {2}
    assert perfil.seen_ids() == {1, 2}
    assert perfil.wanted_ids() == {3}


def test_ler_perfil_inexistente_devolve_perfil_vazio(tmp_path: Path):
    assert ler_perfil(tmp_path / "nada.json").movies == {}


def test_features_of_deriva_decada_do_ano():
    assert features_of(_filme(1, year=1999))["decade"] == (1990,)
    assert features_of(_filme(2, year=None))["decade"] == ()


def test_caracteristica_rara_pesa_mais_que_a_comum():
    # 'comum' está em todos os 10 filmes; 'rara' está só no curtido.
    catalogo = {i: _filme(i, keywords=(100,)) for i in range(1, 11)}
    catalogo[1] = _filme(1, keywords=(100, 200))

    perfil = Profile(movies={1: Entry(seen=True, rating=1, want=False, at="2026-08-20")})
    gosto = construir_gosto(perfil, catalogo)

    assert gosto.weights[("keyword", 200)] > gosto.weights[("keyword", 100)]


def test_caracteristica_presente_em_todo_o_catalogo_tem_peso_nulo():
    # idf = log(N / (1+N)) fica negativo por muito pouco; o teste garante que
    # uma característica onipresente não vira sinal forte.
    catalogo = {i: _filme(i, keywords=(100,)) for i in range(1, 11)}
    perfil = Profile(movies={1: Entry(seen=True, rating=1, want=False, at="2026-08-20")})
    gosto = construir_gosto(perfil, catalogo)

    assert abs(gosto.weights[("keyword", 100)]) < 0.1


def test_rejeicao_produz_peso_negativo():
    catalogo = {i: _filme(i) for i in range(1, 11)}
    catalogo[1] = _filme(1, keywords=(200,))

    perfil = Profile(movies={1: Entry(seen=True, rating=-1, want=False, at="2026-08-20")})
    gosto = construir_gosto(perfil, catalogo)

    assert gosto.weights[("keyword", 200)] < 0


def test_suavizacao_impede_conviccao_a_partir_de_uma_observacao():
    catalogo = {i: _filme(i) for i in range(1, 11)}
    catalogo[1] = _filme(1, keywords=(200,))
    perfil = Profile(movies={1: Entry(seen=True, rating=1, want=False, at="2026-08-20")})

    gosto = construir_gosto(perfil, catalogo, k=2.0)
    idf = math.log(10 / 2)
    # afinidade = (1-0)/(1+0+2) = 1/3, e não 1.0
    assert gosto.weights[("keyword", 200)] == pytest.approx(idf / 3)


def test_gosto_de_um_filme_usa_so_aquele_filme():
    catalogo = {i: _filme(i) for i in range(1, 11)}
    catalogo[5] = _filme(5, keywords=(200,), directors=(77,))

    gosto = gosto_de_um_filme(catalogo[5], catalogo)

    assert gosto.n_ratings == 1
    assert gosto.weights[("director", 77)] > 0


def test_contagem_de_avaliacoes_ignora_filmes_fora_do_catalogo():
    catalogo = {1: _filme(1)}
    perfil = Profile(
        movies={
            1: Entry(seen=True, rating=1, want=False, at="2026-08-20"),
            999: Entry(seen=True, rating=1, want=False, at="2026-08-20"),
        }
    )
    assert construir_gosto(perfil, catalogo).n_ratings == 1

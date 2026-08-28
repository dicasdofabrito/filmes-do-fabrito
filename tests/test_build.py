import json
from pathlib import Path

import pytest

from sync.build import IndiceGrandeDemais, escrever_site_data
from sync.catalog import Movie
from sync.config import Build
from sync.score import Scoring
from sync.shelves import Shelf


def _filme(id_, *, keywords=(), vote_count=1000, theatrical=False) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=2000, runtime=100,
        genres=(18,), keywords=tuple(keywords),
        vote_average=7.0, vote_count=vote_count,
        directors=(), cast=(), language="en",
        track="acervo", theatrical=theatrical, added="2026-08-27",
    )


def _pontuacao(scores: dict[int, float]) -> Scoring:
    return Scoring(scores=scores, affinities=dict(scores), qualities=dict(scores))


def test_escreve_os_tres_arquivos(tmp_path: Path):
    catalogo = {1: _filme(1, keywords=(900,))}
    escrever_site_data(
        tmp_path, catalogo, _pontuacao({1: 0.5}),
        [Shelf("novos", "Entrou hoje", (1,))], Build(6.0, 24),
    )

    assert (tmp_path / "index.json").exists()
    assert (tmp_path / "shelves.json").exists()
    assert (tmp_path / "keywords.json").exists()


def test_index_vem_ordenado_por_score_decrescente(tmp_path: Path):
    catalogo = {1: _filme(1), 2: _filme(2), 3: _filme(3)}
    escrever_site_data(
        tmp_path, catalogo, _pontuacao({1: 0.1, 2: 0.9, 3: 0.5}), [], Build(6.0, 24)
    )

    dados = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [m["id"] for m in dados["movies"]] == [2, 3, 1]


def test_indice_invertido_agrupa_por_keyword(tmp_path: Path):
    catalogo = {1: _filme(1, keywords=(900,)), 2: _filme(2, keywords=(900, 901))}
    escrever_site_data(tmp_path, catalogo, _pontuacao({1: 0.5, 2: 0.5}), [], Build(6.0, 24))

    dados = json.loads((tmp_path / "keywords.json").read_text(encoding="utf-8"))
    assert sorted(dados["900"]) == [1, 2]
    assert dados["901"] == [2]


def test_falha_quando_o_indice_passa_do_limite(tmp_path: Path):
    catalogo = {i: _filme(i) for i in range(500)}
    with pytest.raises(IndiceGrandeDemais):
        escrever_site_data(
            tmp_path, catalogo, _pontuacao({i: 0.5 for i in range(500)}),
            [], Build(0.00001, 24),
        )


def test_score_e_arredondado(tmp_path: Path):
    catalogo = {1: _filme(1)}
    escrever_site_data(tmp_path, catalogo, _pontuacao({1: 0.123456789}), [], Build(6.0, 24))

    dados = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert dados["movies"][0]["s"] == 0.1235


def test_index_carrega_vote_count_e_theatrical(tmp_path: Path):
    """C2: o onboarding de partida a frio precisa de 'n' (vote_count) pra
    calcular os 200 filmes mais votados, e a fileira 'Nos cinemas' precisa
    de 'th' — nenhum dos dois pode ficar de fora do index.json."""
    catalogo = {
        1: _filme(1, vote_count=25431, theatrical=True),
        2: _filme(2, vote_count=0, theatrical=False),
    }
    escrever_site_data(
        tmp_path, catalogo, _pontuacao({1: 0.9, 2: 0.1}), [], Build(6.0, 24)
    )

    dados = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    por_id = {m["id"]: m for m in dados["movies"]}
    assert por_id[1]["n"] == 25431
    assert por_id[1]["th"] is True
    assert por_id[2]["n"] == 0
    assert por_id[2]["th"] is False

import json
from pathlib import Path

import pytest

from sync.build import IndiceGrandeDemais, escrever_site_data, calcular_offsets
from sync.catalog import Movie, escrever_catalogo
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
    catalogo_dict = {1: _filme(1, keywords=(900,))}
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", catalogo_dict.values())
    site_dir = tmp_path / "site"
    escrever_site_data(
        site_dir, catalogo_dict, _pontuacao({1: 0.5}),
        [Shelf("novos", "Entrou hoje", (1,))], Build(6.0, 24),
    )

    assert (site_dir / "index.json").exists()
    assert (site_dir / "shelves.json").exists()
    assert (site_dir / "keywords.json").exists()
    assert (site_dir / "offsets.json").exists()


def test_index_vem_ordenado_por_score_decrescente(tmp_path: Path):
    catalogo = {1: _filme(1), 2: _filme(2), 3: _filme(3)}
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", catalogo.values())
    site_dir = tmp_path / "site"
    escrever_site_data(
        site_dir, catalogo, _pontuacao({1: 0.1, 2: 0.9, 3: 0.5}), [], Build(6.0, 24)
    )

    dados = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
    assert [m["id"] for m in dados["movies"]] == [2, 3, 1]


def test_indice_invertido_agrupa_por_keyword(tmp_path: Path):
    catalogo = {1: _filme(1, keywords=(900,)), 2: _filme(2, keywords=(900, 901))}
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", catalogo.values())
    site_dir = tmp_path / "site"
    escrever_site_data(site_dir, catalogo, _pontuacao({1: 0.5, 2: 0.5}), [], Build(6.0, 24))

    dados = json.loads((site_dir / "keywords.json").read_text(encoding="utf-8"))
    assert sorted(dados["900"]) == [1, 2]
    assert dados["901"] == [2]


def test_falha_quando_o_indice_passa_do_limite(tmp_path: Path):
    catalogo = {i: _filme(i) for i in range(500)}
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", catalogo.values())
    site_dir = tmp_path / "site"
    with pytest.raises(IndiceGrandeDemais):
        escrever_site_data(
            site_dir, catalogo, _pontuacao({i: 0.5 for i in range(500)}),
            [], Build(0.00001, 24),
        )


def test_score_e_arredondado(tmp_path: Path):
    catalogo = {1: _filme(1)}
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", catalogo.values())
    site_dir = tmp_path / "site"
    escrever_site_data(site_dir, catalogo, _pontuacao({1: 0.123456789}), [], Build(6.0, 24))

    dados = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
    assert dados["movies"][0]["s"] == 0.1235


def test_index_carrega_vote_count_e_theatrical(tmp_path: Path):
    """C2: o onboarding de partida a frio precisa de 'n' (vote_count) pra
    calcular os 200 filmes mais votados, e a fileira 'Nos cinemas' precisa
    de 'th' — nenhum dos dois pode ficar de fora do index.json."""
    catalogo = {
        1: _filme(1, vote_count=25431, theatrical=True),
        2: _filme(2, vote_count=0, theatrical=False),
    }
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", catalogo.values())
    site_dir = tmp_path / "site"
    escrever_site_data(
        site_dir, catalogo, _pontuacao({1: 0.9, 2: 0.1}), [], Build(6.0, 24)
    )

    dados = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
    por_id = {m["id"]: m for m in dados["movies"]}
    assert por_id[1]["n"] == 25431
    assert por_id[1]["th"] is True
    assert por_id[2]["n"] == 0
    assert por_id[2]["th"] is False


def test_index_carrega_poster_diretor_elenco_e_idioma(tmp_path: Path):
    filme = Movie(
        id=1, title="F1", year=2000, runtime=100, genres=(18,), keywords=(),
        vote_average=7.0, vote_count=1000, directors=(9339,), cast=(6384, 2975),
        language="en", track="acervo", theatrical=False, added="2026-08-27",
        poster_path="/matrix.jpg", overview="sinopse",
    )
    escrever_catalogo(tmp_path / "data" / "catalog.jsonl", [filme])
    site_dir = tmp_path / "site"
    escrever_site_data(
        site_dir, {1: filme}, _pontuacao({1: 0.5}), [], Build(6.0, 24)
    )
    dados = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
    linha = dados["movies"][0]
    assert linha["p"] == "/matrix.jpg"
    assert linha["d"] == [9339]
    assert linha["c"] == [6384, 2975]
    assert linha["l"] == "en"
    # sinopse NUNCA vai pro index -- só pro catalog.jsonl (decisão #2 do
    # documento de design: uma sinopse por filme pesaria demais no índice).
    assert "ov" not in linha


def test_calcular_offsets_reproduz_a_linha_exata(tmp_path: Path):
    catalogo = tmp_path / "data" / "catalog.jsonl"
    catalogo.parent.mkdir(parents=True)
    filmes = [
        _filme(1, keywords=(900,)),
        _filme(2, keywords=(900, 901)),
        _filme(3),
    ]
    escrever_catalogo(catalogo, filmes)

    offsets = calcular_offsets(catalogo)

    bruto = catalogo.read_bytes()
    for filme in filmes:
        inicio, fim = offsets[filme.id]
        trecho = bruto[inicio : fim + 1]
        linha = json.loads(trecho.decode("utf-8"))
        assert linha["id"] == filme.id
        # a linha capturada termina em quebra de linha, como escrita
        assert trecho.endswith(b"\n")


def test_offsets_json_e_publicado_no_destino(tmp_path: Path):
    catalogo_dir = tmp_path / "data"
    catalogo_dir.mkdir()
    escrever_catalogo(catalogo_dir / "catalog.jsonl", [_filme(1), _filme(2)])

    site_dir = tmp_path / "site"
    escrever_site_data(
        site_dir, {1: _filme(1), 2: _filme(2)},
        _pontuacao({1: 0.5, 2: 0.5}), [], Build(6.0, 24),
    )

    offsets = json.loads((site_dir / "offsets.json").read_text(encoding="utf-8"))
    assert set(offsets.keys()) == {"1", "2"}
    assert len(offsets["1"]) == 2


def test_calcular_offsets_com_titulo_multibyte_utf8(tmp_path: Path):
    """Verifica que offsets funcionam corretamente com títulos contendo
    caracteres acentuados portugueses (multi-byte em UTF-8). Isso garante que
    o cálculo não está contando caracteres em vez de bytes."""
    catalogo_path = tmp_path / "data" / "catalog.jsonl"
    catalogo_path.parent.mkdir(parents=True)

    filmes = [
        Movie(
            id=1, title="Câmera Escondida", year=2000, runtime=100,
            genres=(18,), keywords=(), vote_average=7.0, vote_count=1000,
            directors=(), cast=(), language="pt", track="acervo",
            theatrical=False, added="2026-08-27",
        ),
        Movie(
            id=2, title="Beleza Não Tão Pura", year=2001, runtime=110,
            genres=(18,), keywords=(), vote_average=7.5, vote_count=2000,
            directors=(), cast=(), language="pt", track="acervo",
            theatrical=False, added="2026-08-28",
        ),
        Movie(
            id=3, title="Ação com Açúcar", year=2002, runtime=120,
            genres=(28,), keywords=(), vote_average=8.0, vote_count=3000,
            directors=(), cast=(), language="pt", track="acervo",
            theatrical=False, added="2026-08-29",
        ),
    ]
    escrever_catalogo(catalogo_path, filmes)

    offsets = calcular_offsets(catalogo_path)

    bruto = catalogo_path.read_bytes()
    for filme in filmes:
        inicio, fim = offsets[filme.id]
        trecho = bruto[inicio : fim + 1]
        linha = json.loads(trecho.decode("utf-8"))
        assert linha["id"] == filme.id
        assert linha["t"] == filme.title
        assert trecho.endswith(b"\n")

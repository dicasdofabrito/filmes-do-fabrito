from pathlib import Path

from sync.catalog import Movie, escrever_catalogo, ler_catalogo, montar_filme


def _filme(id_: int = 603, **extras) -> Movie:
    base = dict(
        id=id_,
        title="Matrix",
        year=1999,
        runtime=136,
        genres=(28, 878),
        keywords=(1701, 9743),
        vote_average=8.2,
        vote_count=25431,
        directors=(9339,),
        cast=(6384, 2975),
        language="en",
        track="acervo",
        theatrical=False,
        added="2026-08-27",
    )
    return Movie(**{**base, **extras})


def test_ida_e_volta_pela_linha_preserva_o_filme():
    original = _filme()
    assert Movie.from_row(original.to_row()) == original


def test_a_linha_usa_chaves_abreviadas():
    linha = _filme().to_row()
    assert linha["t"] == "Matrix"
    assert linha["k"] == [1701, 9743]
    assert "title" not in linha


def test_escrita_ordena_por_id(tmp_path: Path):
    destino = tmp_path / "catalog.jsonl"
    escrever_catalogo(destino, [_filme(300), _filme(100), _filme(200)])

    lidos = list(ler_catalogo(destino))
    assert lidos == [100, 200, 300]


def test_leitura_de_arquivo_inexistente_devolve_vazio(tmp_path: Path):
    assert ler_catalogo(tmp_path / "nao_existe.jsonl") == {}


def test_from_row_tolera_added_ausente():
    """B9: um catalog.jsonl gravado antes do campo `a` existir não pode
    ficar ilegível — degrada para string vazia."""
    linha = _filme().to_row()
    del linha["a"]
    assert Movie.from_row(linha).added == ""


def test_montar_filme_extrai_diretor_e_elenco_do_credits():
    detalhe = {
        "id": 603,
        "title": "Matrix",
        "release_date": "1999-03-31",
        "runtime": 136,
        "genres": [{"id": 28}, {"id": 878}],
        "keywords": {"keywords": [{"id": 1701}]},
        "vote_average": 8.2,
        "vote_count": 25431,
        "original_language": "en",
        "credits": {
            "cast": [{"id": i} for i in range(10)],
            "crew": [
                {"id": 9339, "job": "Director"},
                {"id": 111, "job": "Producer"},
            ],
        },
    }
    filme = montar_filme(detalhe, track="acervo", theatrical=False, added="2026-08-27")

    assert filme.directors == (9339,)
    assert filme.cast == (0, 1, 2, 3, 4)  # só os cinco primeiros
    assert filme.year == 1999
    assert filme.keywords == (1701,)


def test_montar_filme_tolera_campos_ausentes():
    filme = montar_filme(
        {"id": 7, "title": "X"}, track="recente", theatrical=True, added="2026-08-27"
    )
    assert filme.year is None
    assert filme.keywords == ()
    assert filme.directors == ()

from datetime import date

from sync.catalog import Movie
from sync.config import Build, Config, Motor, Admissao
from sync.profile import Entry, Profile, Taste
from sync.score import Scoring
from sync.shelves import Contexto, montar_fileiras

HOJE = date(2026, 8, 27)
PESOS = {
    "keyword": 0.40, "director": 0.20, "cast": 0.15,
    "genre": 0.15, "decade": 0.06, "language": 0.04,
}


def _cfg(fileiras: tuple[str, ...]) -> Config:
    return Config(
        admissao=Admissao(50, 18, 5, 8.0, 60),
        motor=Motor(2.0, 500, 0.75, 10, PESOS),
        build=Build(6.0, 3),
        fileiras=fileiras,
    )


def _filme(id_, *, year=2000, runtime=100, theatrical=False, added="2020-01-01",
           keywords=(), directors=(), genres=()) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=runtime,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=7.0, vote_count=1000,
        directors=tuple(directors), cast=(), language="en",
        track="acervo", theatrical=theatrical, added=added,
    )


def _ctx(catalogo, perfil, fileiras, *, scores=None, gosto=None) -> Contexto:
    scores = scores or {i: 0.5 for i in catalogo}
    return Contexto(
        catalogo=catalogo,
        perfil=perfil,
        pontuacao=Scoring(scores=scores, affinities=dict(scores), qualities=dict(scores)),
        gosto=gosto or Taste(weights={}, n_ratings=40),
        hoje=HOJE,
        cfg=_cfg(fileiras),
        vibes={"fim do mundo": [900]},
        nomes={"director": {77: "Tarkovsky"}, "cast": {}},
    )


def test_watchlist_traz_apenas_os_marcados_como_quero_ver():
    catalogo = {1: _filme(1), 2: _filme(2)}
    perfil = Profile(movies={2: Entry(want=True, at="2026-08-01")})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("watchlist",)))

    assert fileiras[0].key == "watchlist"
    assert fileiras[0].movie_ids == (2,)


def test_novos_traz_apenas_os_admitidos_hoje():
    catalogo = {
        1: _filme(1, added="2026-08-27"),
        2: _filme(2, added="2026-08-26"),
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("novos",)))
    assert fileiras[0].movie_ids == (1,)


def test_cinemas_traz_apenas_os_em_cartaz():
    catalogo = {1: _filme(1, theatrical=True), 2: _filme(2)}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("cinemas",)))
    assert fileiras[0].movie_ids == (1,)


def test_curto_filtra_por_duracao_e_exclui_vistos():
    catalogo = {1: _filme(1, runtime=95), 2: _filme(2, runtime=140), 3: _filme(3, runtime=90)}
    perfil = Profile(movies={3: Entry(seen=True, at="2026-08-01")})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("curto",)))

    assert fileiras[0].movie_ids == (1,)


def test_classicos_exige_25_anos_e_ausencia_no_perfil():
    catalogo = {
        1: _filme(1, year=1990),
        2: _filme(2, year=2020),
        3: _filme(3, year=1985),
    }
    perfil = Profile(movies={3: Entry(seen=True, at="2026-08-01")})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("classicos",)))

    assert fileiras[0].movie_ids == (1,)


def test_diretor_usa_o_de_maior_peso_no_gosto():
    catalogo = {
        1: _filme(1, directors=(77,)),
        2: _filme(2, directors=(88,)),
        3: _filme(3, directors=(77,)),
    }
    perfil = Profile(movies={3: Entry(seen=True, at="2026-08-01")})
    gosto = Taste(weights={("director", 77): 2.0, ("director", 88): 0.1}, n_ratings=40)

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("diretor",), gosto=gosto))

    assert fileiras[0].movie_ids == (1,)
    assert "Tarkovsky" in fileiras[0].title


def test_vibe_e_estavel_no_mesmo_dia_e_filtra_por_keyword():
    catalogo = {1: _filme(1, keywords=(900,)), 2: _filme(2, keywords=(1,))}
    ctx = _ctx(catalogo, Profile(), ("vibe",))

    primeira = montar_fileiras(ctx)[0]
    segunda = montar_fileiras(ctx)[0]

    assert primeira.title == segunda.title
    assert primeira.movie_ids == (1,)


def test_fileira_vazia_e_omitida():
    catalogo = {1: _filme(1)}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("watchlist", "novos")))
    assert fileiras == []


def test_respeita_a_ordem_configurada():
    catalogo = {1: _filme(1, theatrical=True, added="2026-08-27")}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("cinemas", "novos")))
    assert [f.key for f in fileiras] == ["cinemas", "novos"]


def test_tamanho_da_fileira_respeita_o_config():
    catalogo = {i: _filme(i, added="2026-08-27") for i in range(1, 11)}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("novos",)))
    assert len(fileiras[0].movie_ids) == 3  # Build.tamanho_fileira do _cfg

from datetime import date

from sync.catalog import Movie
from sync.config import Build, Config, Motor, Admissao
from sync.profile import Entry, Profile, Taste
from sync.score import Scoring
from sync.shelves import Contexto, _percentil, montar_fileiras

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
           keywords=(), directors=(), genres=(), language="en") -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=runtime,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=7.0, vote_count=1000,
        directors=tuple(directors), cast=(), language=language,
        track="acervo", theatrical=theatrical, added=added,
    )


def _ctx(
    catalogo, perfil, fileiras, *,
    scores=None, affinities=None, qualities=None, gosto=None,
) -> Contexto:
    scores = scores or {i: 0.5 for i in catalogo}
    afinidades = affinities if affinities is not None else dict(scores)
    qualidades = qualities if qualities is not None else dict(scores)
    return Contexto(
        catalogo=catalogo,
        perfil=perfil,
        pontuacao=Scoring(scores=scores, affinities=afinidades, qualities=qualidades),
        gosto=gosto or Taste(weights={}, n_ratings=40),
        hoje=HOJE,
        cfg=_cfg(fileiras),
        vibes={"fim do mundo": [900]},
        nomes={"director": {77: "Tarkovsky"}, "cast": {}},
    )


def _filme_com_idioma(id_, *, year, genres, language) -> Movie:
    """Constrói um filme com idioma explícito — o helper `_filme` fixa
    `language="en"`, o que não serve para testar a dimensão idioma."""
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=100,
        genres=tuple(genres), keywords=(), vote_average=7.0, vote_count=1000,
        directors=(), cast=(), language=language,
        track="acervo", theatrical=False, added="2020-01-01",
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



def test_percentil_calcula_o_indice_correto():
    valores = [10, 20, 30, 40, 50]
    assert _percentil(valores, 0.0) == 10
    assert _percentil(valores, 0.5) == 30
    assert _percentil(valores, 0.99) == 50
    assert _percentil([], 0.5) == 0.0


def test_ordenar_devolve_em_ordem_decrescente_de_score():
    catalogo = {1: _filme(1), 2: _filme(2), 3: _filme(3)}
    perfil = Profile(movies={
        1: Entry(want=True, at="2026-08-01"),
        2: Entry(want=True, at="2026-08-01"),
        3: Entry(want=True, at="2026-08-01"),
    })
    scores = {1: 0.2, 2: 0.9, 3: 0.5}

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("watchlist",), scores=scores))

    assert fileiras[0].movie_ids == (2, 3, 1)


def test_classicos_e_aposta_nao_ficam_vazias_quando_os_melhores_estao_vistos():
    """O corte de qualidade tem que ser calculado sobre a população elegível
    da própria fileira (filmes não vistos), não sobre o catálogo inteiro —
    senão os filmes de maior nota, uma vez vistos, tiram do alcance qualquer
    filme ainda elegível."""
    catalogo = {i: _filme(i) for i in range(1, 11)}
    qualidades = {i: 0.40 + i * 0.02 for i in range(1, 11)}
    perfil = Profile(movies={
        9: Entry(seen=True, at="2026-08-01"),
        10: Entry(seen=True, at="2026-08-01"),
    })

    fileiras = montar_fileiras(
        _ctx(catalogo, perfil, ("aposta", "classicos"), qualities=qualidades)
    )

    por_chave = {f.key: f for f in fileiras}
    assert "aposta" in por_chave
    assert "classicos" in por_chave
    assert por_chave["aposta"].movie_ids == (8,)
    assert por_chave["classicos"].movie_ids == (8,)


def test_aposta_exige_afinidade_mediana_e_qualidade_alta():
    catalogo = {i: _filme(i) for i in range(1, 6)}
    afinidades = {1: 0.10, 2: 0.90, 3: 0.50, 4: 0.55, 5: 0.45}
    qualidades = {1: 0.30, 2: 0.99, 3: 0.99, 4: 0.10, 5: 0.20}

    fileiras = montar_fileiras(
        _ctx(catalogo, Profile(), ("aposta",), affinities=afinidades, qualities=qualidades)
    )

    # id 3: afinidade dentro da faixa 40-70% e qualidade no top 5% -> entra.
    # id 2: afinidade altíssima (fora da faixa), mesmo com qualidade alta -> fora.
    # id 4: dentro da faixa de afinidade, mas qualidade medíocre -> fora.
    assert fileiras[0].movie_ids == (3,)


def test_ponto_cego_ignora_dimensao_abaixo_do_piso_populacional():
    catalogo = {}
    for i in range(1, 201):  # dimensão elegível: genre 900 tem 200 filmes
        idioma = "en" if i % 2 == 0 else "pt"
        ano = 2005 if i % 2 == 0 else 1995
        catalogo[i] = _filme_com_idioma(i, year=ano, genres=(900,), language=idioma)
    for i in range(201, 251):  # dimensão abaixo do piso: genre 5 tem só 50 filmes
        catalogo[i] = _filme_com_idioma(i, year=2015, genres=(5,), language="fr")

    # 20 dos 200 filmes de genre 900 curtidos (razão 0.10); nenhum dos 50 de
    # genre 5 curtido (razão 0.0 — mais "pouco assistida" ainda, mas abaixo
    # do piso populacional e por isso nunca elegível como ponto cego).
    perfil = Profile(movies={i: Entry(rating=1, at="2026-08-01") for i in range(1, 21)})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("ponto_cego",)))

    assert fileiras[0].key == "ponto_cego"
    assert len(fileiras[0].movie_ids) == 3  # Build.tamanho_fileira do _cfg
    assert all(900 in catalogo[i].genres for i in fileiras[0].movie_ids)
    assert not any(5 in catalogo[i].genres for i in fileiras[0].movie_ids)


def test_similar_usa_ancora_de_qualidade_quando_afinidade_empata():
    """D1: _similar precisa usar a mesma maquinaria do motor principal —
    afinidade normalizada combinada com a âncora de qualidade, no mesmo
    split de `peso_afinidade`. Aqui os dois candidatos compartilham a
    keyword da referência (afinidade empatada, amplitude zero), então o
    desempate só pode vir da qualidade — antes dessa correção, `_similar`
    ordenava por afinidade crua e ignorava qualidade por completo,
    deixando o empate à mercê da ordem arbitrária de um `set`."""
    referencia = _filme(1, keywords=(900,))
    candidato_qualidade_alta = _filme(2, keywords=(900,))
    candidato_qualidade_baixa = _filme(3, keywords=(900,))
    catalogo = {
        1: referencia,
        2: candidato_qualidade_alta,
        3: candidato_qualidade_baixa,
    }
    perfil = Profile(movies={1: Entry(seen=True, rating=1, at="2026-08-01")})

    fileiras = montar_fileiras(
        _ctx(
            catalogo,
            perfil,
            ("similar",),
            qualities={1: 0.5, 2: 0.9, 3: 0.1},
        )
    )

    assert fileiras[0].key == "similar"
    assert fileiras[0].movie_ids == (2, 3)


def test_estrangeiros_traz_apenas_idiomas_fora_de_en_pt_es():
    catalogo = {
        1: _filme(1, language="en"),
        2: _filme(2, language="ja"),
        3: _filme(3, language="pt"),
        4: _filme(4, language="fr"),
        5: _filme(5, language="es"),
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("estrangeiros",)))
    assert set(fileiras[0].movie_ids) == {2, 4}


def test_antigos_traz_apenas_filmes_com_mais_de_40_anos():
    catalogo = {
        1: _filme(1, year=1986),  # hoje.year - year == 40, nao entra (exclusivo)
        2: _filme(2, year=1985),  # 41 anos, entra
        3: _filme(3, year=2000),  # nao entra
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("antigos",)))
    assert fileiras[0].movie_ids == (2,)


def test_antigos_nao_traz_filme_que_tambem_e_estrangeiro():
    """Filme velho E estrangeiro vai só pra 'Filmes estrangeiros' -- idioma
    tem prioridade sobre idade quando os dois se aplicam ao mesmo filme."""
    catalogo = {1: _filme(1, year=1980, language="ja")}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("antigos", "estrangeiros")))
    por_chave = {f.key: f for f in fileiras}
    assert "antigos" not in por_chave
    assert por_chave["estrangeiros"].movie_ids == (1,)


def test_estrangeiros_e_antigos_saem_das_fileiras_de_descoberta_normais():
    catalogo = {
        1: _filme(1, runtime=90, language="ja"),  # estrangeiro
        2: _filme(2, runtime=90, year=1980),  # antigo
        3: _filme(3, runtime=90),  # elegivel normal
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("curto",)))
    assert fileiras[0].movie_ids == (3,)


def test_cinemas_exclui_estrangeiros_e_antigos():
    catalogo = {
        1: _filme(1, theatrical=True),
        2: _filme(2, theatrical=True, language="ja"),
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("cinemas",)))
    assert fileiras[0].movie_ids == (1,)


def test_classicos_nao_inclui_filmes_com_mais_de_40_anos_nem_estrangeiros():
    catalogo = {
        1: _filme(1, year=2000),  # 26 anos, classico normal
        2: _filme(2, year=1980),  # 46 anos, vai pra "antigos"
        3: _filme(3, year=2000, language="ja"),  # classico mas estrangeiro
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("classicos",)))
    assert fileiras[0].movie_ids == (1,)


def test_watchlist_ignora_exclusao_de_estrangeiro_e_antigo():
    catalogo = {1: _filme(1, year=1970, language="ja")}
    perfil = Profile(movies={1: Entry(want=True, at="2026-08-01")})
    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("watchlist",)))
    assert fileiras[0].movie_ids == (1,)


def test_similar_exclui_a_referencia_e_os_ja_vistos():
    referencia = _filme(1, keywords=(900,))
    ja_visto = _filme(2, keywords=(900,))
    candidato = _filme(3, keywords=(900,))
    catalogo = {1: referencia, 2: ja_visto, 3: candidato}
    perfil = Profile(
        movies={
            1: Entry(seen=True, rating=1, at="2026-08-01"),
            2: Entry(seen=True, at="2026-08-01"),
        }
    )

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("similar",)))

    assert fileiras[0].movie_ids == (3,)

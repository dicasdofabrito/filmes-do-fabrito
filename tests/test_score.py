from sync.catalog import Movie
from sync.config import Motor
from sync.profile import Taste
from sync.score import afinidade, pontuar, qualidade_bayesiana

PESOS = {
    "keyword": 0.40, "director": 0.20, "cast": 0.15,
    "genre": 0.15, "decade": 0.06, "language": 0.04,
}


def _motor(**extras) -> Motor:
    base = dict(
        suavizacao_k=2.0, qualidade_m=500, peso_afinidade=0.75,
        min_avaliacoes=10, pesos=PESOS,
    )
    return Motor(**{**base, **extras})


def _filme(id_=1, *, keywords=(), genres=(), year=None, media=7.0, votos=100) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=100,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=media, vote_count=votos,
        directors=(), cast=(), language="",
        track="acervo", theatrical=False, added="2026-08-27",
    )


def test_filme_sem_keywords_nao_e_penalizado():
    """O teste central da redistribuição de peso.

    Dois filmes com o mesmo sinal de gênero: um tem keyword igualmente
    positiva, o outro não tem keyword nenhuma. O segundo não pode afundar
    só porque o TMDB não catalogou suas palavras-chave.
    """
    gosto = Taste(weights={("genre", 18): 1.0, ("keyword", 200): 1.0}, n_ratings=20)

    completo = _filme(1, genres=(18,), keywords=(200,))
    sem_keyword = _filme(2, genres=(18,))

    assert afinidade(completo, gosto, PESOS) == 1.0
    assert afinidade(sem_keyword, gosto, PESOS) == 1.0


def test_sem_redistribuicao_o_valor_seria_muito_menor():
    # Guarda contra uma regressão para a implementação ingênua, que daria
    # 0.15 (só a fatia do gênero) em vez de 1.0.
    gosto = Taste(weights={("genre", 18): 1.0}, n_ratings=20)
    assert afinidade(_filme(1, genres=(18,)), gosto, PESOS) > 0.9


def test_afinidade_e_zero_quando_nao_ha_caracteristica_conhecida():
    gosto = Taste(weights={("genre", 99): 1.0}, n_ratings=20)
    assert afinidade(_filme(1, genres=(18,)), gosto, PESOS) == 0.0


def test_afinidade_negativa_quando_o_sinal_e_de_rejeicao():
    gosto = Taste(weights={("genre", 18): -1.0}, n_ratings=20)
    assert afinidade(_filme(1, genres=(18,)), gosto, PESOS) < 0


def test_qualidade_puxa_poucos_votos_para_a_media_global():
    alto_e_raro = qualidade_bayesiana(9.8, 51, m=500, media_global=6.0)
    alto_e_consolidado = qualidade_bayesiana(8.2, 25000, m=500, media_global=6.0)

    assert alto_e_raro < alto_e_consolidado


def test_partida_a_frio_ignora_a_afinidade():
    catalogo = {
        1: _filme(1, genres=(18,), media=9.0, votos=10000),
        2: _filme(2, genres=(18,), media=5.0, votos=10000),
    }
    gosto = Taste(weights={("genre", 18): 5.0}, n_ratings=3)

    resultado = pontuar(catalogo, gosto, _motor())

    # Com menos de 10 avaliações o score é qualidade pura, então o filme de
    # nota alta vence mesmo que ambos tenham a mesma afinidade.
    assert resultado.scores[1] > resultado.scores[2]
    assert resultado.affinities[1] == resultado.affinities[2]


def test_com_perfil_maduro_a_afinidade_domina():
    catalogo = {
        1: _filme(1, genres=(18,), media=6.0, votos=10000),
        2: _filme(2, genres=(99,), media=8.0, votos=10000),
    }
    gosto = Taste(weights={("genre", 18): 5.0, ("genre", 99): -5.0}, n_ratings=40)

    resultado = pontuar(catalogo, gosto, _motor())

    assert resultado.scores[1] > resultado.scores[2]


def test_scores_ficam_entre_zero_e_um():
    catalogo = {i: _filme(i, genres=(18,), media=float(i), votos=1000) for i in range(1, 9)}
    gosto = Taste(weights={("genre", 18): 1.0}, n_ratings=40)

    resultado = pontuar(catalogo, gosto, _motor())

    assert all(0.0 <= s <= 1.0 for s in resultado.scores.values())


def test_catalogo_vazio_nao_quebra():
    resultado = pontuar({}, Taste(weights={}, n_ratings=40), _motor())
    assert resultado.scores == {}


def test_amplitude_zero_com_dois_filmes_iguais_volta_ao_qualidade():
    """Quando a afinidade é idêntica em todos os filmes, o score não deve ser
    comprimido para 25% da qualidade. Deve ser exatamente a qualidade.

    Dois filmes com mesmos gêneros, perfil maduro (n_ratings=40 > 10),
    mas notas muito diferentes. A amplitude de afinidade é zero porque
    ambos têm a mesma característica. O score deve ser a qualidade pura,
    e o filme de nota mais alta deve vencer.
    """
    catalogo = {
        1: _filme(1, genres=(18,), media=8.5, votos=10000),
        2: _filme(2, genres=(18,), media=5.0, votos=10000),
    }
    gosto = Taste(weights={("genre", 18): 1.0}, n_ratings=40)

    resultado = pontuar(catalogo, gosto, _motor())

    # Os scores devem ser iguais às qualidades (amplitude zero cai para qualidade pura)
    assert resultado.scores[1] == resultado.qualities[1]
    assert resultado.scores[2] == resultado.qualities[2]

    # O filme com melhor qualidade ainda vence
    assert resultado.scores[1] > resultado.scores[2]


def test_catalogo_um_filme_nao_quebra_com_perfil_maduro():
    """Um catálogo com apenas um filme não deve quebrar, mesmo com perfil maduro.
    A amplitude é zero (não há min e max distintos), então cai para qualidade pura.
    """
    catalogo = {1: _filme(1, genres=(18,), media=7.5, votos=10000)}
    gosto = Taste(weights={("genre", 18): 1.0}, n_ratings=40)

    resultado = pontuar(catalogo, gosto, _motor())

    # Não deve quebrar
    assert resultado.scores[1] == resultado.qualities[1]
    assert 0.0 <= resultado.scores[1] <= 1.0

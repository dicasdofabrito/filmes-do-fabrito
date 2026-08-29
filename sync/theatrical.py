"""Classificação 'só no cinema' a partir dos release_dates do TMDB."""

from __future__ import annotations

from datetime import date

# Tipos do TMDB: 1 premiere, 2 limitado, 3 teatral, 4 digital, 5 físico, 6 TV.
TIPO_TEATRAL = 3
TIPOS_DOMESTICOS = frozenset({4, 5})

# Nenhuma janela de exclusividade de sala real passa disso. Uma estreia mais
# antiga que isso sem lançamento doméstico registrado em lugar nenhum quase
# sempre é uma lacuna de dado do TMDB (comum em clássicos e filmes antigos),
# não um filme genuinamente ainda só em cartaz.
JANELA_TEATRAL_DIAS = 730


def _data(entrada: dict) -> date | None:
    bruto = (entrada.get("release_date") or "")[:10]
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def apenas_no_cinema(
    release_dates: dict, hoje: date, *, regiao: str = "BR"
) -> bool:
    """True se o filme já estreou em sala no país e ainda não saiu em casa
    em NENHUM mercado.

    A estreia em sala é verificada só na região do Fabio (BR) — é o que
    define "ele pode ir ao cinema hoje". Mas o lançamento doméstico é
    verificado em TODOS os países do payload, não só no BR: a cobertura do
    TMDB para datas de digital/físico no Brasil é muito mais esparsa que a
    de sala, e sem essa checagem global clássicos de décadas atrás (Ben-Hur,
    Drácula) ficam presos em "Nos cinemas" para sempre só porque o TMDB
    nunca registrou uma data de lançamento doméstico especificamente para o
    Brasil. Na prática, se saiu em digital ou físico em qualquer lugar do
    mundo, o Fabio consegue acessar.

    Datas futuras são ignoradas nos dois lados: uma estreia anunciada ainda
    não é 'em cartaz', e um digital agendado ainda não é 'disponível'.
    """
    estreia_mais_recente: date | None = None
    for pais in release_dates.get("results", []):
        if pais.get("iso_3166_1") != regiao:
            continue
        for entrada in pais.get("release_dates", []):
            quando = _data(entrada)
            if quando is None or quando > hoje or entrada.get("type") != TIPO_TEATRAL:
                continue
            if estreia_mais_recente is None or quando > estreia_mais_recente:
                estreia_mais_recente = quando

    if estreia_mais_recente is None:
        return False

    # Estreia velha demais: se o TMDB ainda não tem lançamento doméstico
    # registrado depois de tanto tempo, é lacuna de catalogação, não um
    # filme genuinamente exclusivo de sala.
    if (hoje - estreia_mais_recente).days > JANELA_TEATRAL_DIAS:
        return False

    for pais in release_dates.get("results", []):
        for entrada in pais.get("release_dates", []):
            quando = _data(entrada)
            if quando is not None and quando <= hoje and entrada.get("type") in TIPOS_DOMESTICOS:
                return False

    return True

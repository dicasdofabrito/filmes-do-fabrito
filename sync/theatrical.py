"""Classificação 'só no cinema' a partir dos release_dates do TMDB."""

from __future__ import annotations

from datetime import date

# Tipos do TMDB: 1 premiere, 2 limitado, 3 teatral, 4 digital, 5 físico, 6 TV.
TIPO_TEATRAL = 3
TIPOS_DOMESTICOS = frozenset({4, 5})


def _data(entrada: dict) -> date | None:
    bruto = (entrada.get("release_date") or "")[:10]
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def apenas_no_cinema(
    release_dates: dict, hoje: date, *, regiao: str = "BR"
) -> bool:
    """True se o filme já estreou em sala no país e ainda não saiu em casa.

    Datas futuras são ignoradas nos dois lados: uma estreia anunciada ainda
    não é 'em cartaz', e um digital agendado ainda não é 'disponível'.
    """
    for pais in release_dates.get("results", []):
        if pais.get("iso_3166_1") != regiao:
            continue

        estreou = False
        saiu_em_casa = False

        for entrada in pais.get("release_dates", []):
            quando = _data(entrada)
            if quando is None or quando > hoje:
                continue
            if entrada.get("type") == TIPO_TEATRAL:
                estreou = True
            elif entrada.get("type") in TIPOS_DOMESTICOS:
                saiu_em_casa = True

        return estreou and not saiu_em_casa

    return False

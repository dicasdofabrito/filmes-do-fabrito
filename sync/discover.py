"""Paginação do /discover e contorno do teto de 10.000 resultados."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sync.tmdb import TMDBClient

logger = logging.getLogger(__name__)

TETO_DISCOVER = 10_000
MAX_PAGINAS = 500


async def paginar(
    cliente: TMDBClient,
    path: str,
    params: dict,
    *,
    max_paginas: int = MAX_PAGINAS,
) -> list[dict]:
    """Percorre todas as páginas de um endpoint paginado do TMDB."""
    acumulado: list[dict] = []
    pagina = 1

    while pagina <= max_paginas:
        dados = await cliente.get(path, **params, page=pagina)
        acumulado.extend(dados.get("results", []))

        total_paginas = min(dados.get("total_pages", 1), max_paginas)
        if pagina >= total_paginas:
            break
        pagina += 1

    return acumulado


async def descobrir_fatiado(
    cliente: TMDBClient,
    params: dict,
    *,
    ano_inicial: int = 1874,
    ano_final: int,
) -> list[dict]:
    """Consulta o /discover dividindo por faixa de ano quando necessário.

    O TMDB corta qualquer consulta em 10.000 resultados. Ao detectar que a
    faixa estoura esse teto, ela é dividida ao meio e cada metade é tratada
    recursivamente até caber. Subdivide por datas até chegar a dias, quando
    necessário, para garantir que nenhum resultado seja silenciosamente perdido.
    """
    inicio = date(ano_inicial, 1, 1)
    fim = date(ano_final, 12, 31)
    return await _fatiar_intervalo(cliente, params, inicio, fim)


async def _fatiar_intervalo(
    cliente: TMDBClient,
    params: dict,
    inicio: date,
    fim: date,
) -> list[dict]:
    """Recursivamente fatia por data para contornar o teto de 10.000 resultados.

    Bisecta o intervalo de datas até que cada faixa caiba sob o teto.
    Quando um único dia ainda excede o teto, emite um aviso em vez de levantar,
    pois ano é a granularidade mínima da query.
    """
    faixa = {
        **params,
        "primary_release_date.gte": inicio.isoformat(),
        "primary_release_date.lte": fim.isoformat(),
    }

    sondagem = await cliente.get("/discover/movie", **faixa, page=1)
    total = sondagem.get("total_results", 0)

    if total <= TETO_DISCOVER:
        return await paginar(cliente, "/discover/movie", faixa)

    if inicio == fim:
        # Piso da recursão: um único dia ainda excede o teto.
        # Emite aviso mas retorna os resultados que conseguir.
        logger.warning(
            f"Data {inicio} tem {total} resultados, excedendo o teto de {TETO_DISCOVER}. "
            f"Retornando apenas os primeiros 10.000."
        )
        return await paginar(cliente, "/discover/movie", faixa)

    # Bisecta o intervalo no meio (em dias)
    duracao = fim - inicio
    meio = inicio + duracao // 2
    esquerda = await _fatiar_intervalo(cliente, params, inicio, meio)
    direita = await _fatiar_intervalo(
        cliente, params, meio + timedelta(days=1), fim
    )
    return esquerda + direita

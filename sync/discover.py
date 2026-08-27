"""Paginação do /discover e contorno do teto de 10.000 resultados."""

from __future__ import annotations

from sync.tmdb import TMDBClient

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
    recursivamente até caber.
    """
    faixa = {
        **params,
        "primary_release_date.gte": f"{ano_inicial}-01-01",
        "primary_release_date.lte": f"{ano_final}-12-31",
    }

    sondagem = await cliente.get("/discover/movie", **faixa, page=1)
    total = sondagem.get("total_results", 0)

    if total <= TETO_DISCOVER or ano_inicial >= ano_final:
        return await paginar(cliente, "/discover/movie", faixa)

    meio = (ano_inicial + ano_final) // 2
    esquerda = await descobrir_fatiado(
        cliente, params, ano_inicial=ano_inicial, ano_final=meio
    )
    direita = await descobrir_fatiado(
        cliente, params, ano_inicial=meio + 1, ano_final=ano_final
    )
    return esquerda + direita

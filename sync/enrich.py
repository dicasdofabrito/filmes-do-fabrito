"""Busca em lote dos detalhes completos de filmes."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from sync.tmdb import TMDBClient

CAMPOS_EXTRAS = "keywords,credits,release_dates"


async def buscar_detalhes(
    cliente: TMDBClient, ids: Iterable[int], *, concorrencia: int = 16
) -> list[dict]:
    """Busca /movie/{id} com tudo que o motor precisa, em paralelo limitado.

    Keywords, duração, elenco e diretor não vêm no /discover — só aqui.
    """
    limitador = asyncio.Semaphore(concorrencia)

    async def um(id_: int) -> dict:
        async with limitador:
            return await cliente.get(
                f"/movie/{id_}",
                append_to_response=CAMPOS_EXTRAS,
                language="pt-BR",
            )

    return list(await asyncio.gather(*(um(i) for i in ids)))

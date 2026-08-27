"""Export diário de ids publicado pelo TMDB."""

from __future__ import annotations

import gzip
import json
from datetime import date

import httpx

BASE_EXPORT = "http://files.tmdb.org/p/exports"


def url_export(dia: date) -> str:
    return f"{BASE_EXPORT}/movie_ids_{dia:%m_%d_%Y}.json.gz"


async def baixar_export(
    dia: date, *, client: httpx.AsyncClient | None = None
) -> set[int]:
    """Baixa o export do dia e devolve o conjunto de ids.

    O arquivo é JSONL comprimido: um objeto por linha, não um array.
    """
    proprio = client is None
    cliente = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    try:
        resposta = await cliente.get(url_export(dia))
        resposta.raise_for_status()
        bruto = gzip.decompress(resposta.content)
    finally:
        if proprio:
            await cliente.aclose()

    ids: set[int] = set()
    for linha in bruto.splitlines():
        if linha.strip():
            ids.add(json.loads(linha)["id"])
    return ids


def ids_novos(hoje: set[int], ontem: set[int]) -> set[int]:
    return hoje - ontem

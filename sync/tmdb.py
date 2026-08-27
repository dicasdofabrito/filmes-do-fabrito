"""Único ponto do pipeline que fala com a rede."""

from __future__ import annotations

import asyncio

import httpx

BASE_URL = "https://api.themoviedb.org/3"

# Status que valem uma nova tentativa: limite de taxa e indisponibilidade
# temporária. Qualquer outro erro é definitivo e falha na hora.
STATUS_TEMPORARIOS = {429, 500, 502, 503, 504}


class TMDBError(RuntimeError):
    """Falha definitiva ao falar com o TMDB."""


class TMDBClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        max_retries: int = 5,
        backoff_base: float = 0.5,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "accept": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def __aenter__(self) -> TMDBClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def get(self, path: str, **params: object) -> dict:
        ultima: Exception | None = None

        for tentativa in range(self._max_retries):
            espera = self._backoff_base * (2**tentativa)

            try:
                resposta = await self._client.get(path, params=params)
            except httpx.TransportError as erro:
                ultima = erro
            else:
                if resposta.status_code == 200:
                    return resposta.json()

                if resposta.status_code not in STATUS_TEMPORARIOS:
                    raise TMDBError(
                        f"{resposta.status_code} em {path}: {resposta.text[:200]}"
                    )

                ultima = TMDBError(f"{resposta.status_code} em {path}")
                # O TMDB informa quanto esperar quando limita a taxa.
                cabecalho = resposta.headers.get("Retry-After")
                if cabecalho is not None:
                    try:
                        espera = float(cabecalho)
                    except ValueError:
                        pass

            await asyncio.sleep(espera)

        raise TMDBError(
            f"esgotadas {self._max_retries} tentativas em {path}"
        ) from ultima

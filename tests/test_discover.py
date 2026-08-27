import httpx
import respx

from sync.discover import descobrir_fatiado, paginar
from sync.tmdb import TMDBClient


def _pagina(pagina: int, total_paginas: int, ids: list[int], total: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "page": pagina,
            "total_pages": total_paginas,
            "total_results": total,
            "results": [{"id": i} for i in ids],
        },
    )


@respx.mock
async def test_paginar_junta_todas_as_paginas():
    respx.get("https://api.themoviedb.org/3/discover/movie").mock(
        side_effect=[
            _pagina(1, 2, [1, 2], 4),
            _pagina(2, 2, [3, 4], 4),
        ]
    )
    async with TMDBClient("tok") as cliente:
        resultados = await paginar(cliente, "/discover/movie", {})

    assert [r["id"] for r in resultados] == [1, 2, 3, 4]


@respx.mock
async def test_paginar_respeita_o_teto_de_paginas():
    respx.get("https://api.themoviedb.org/3/discover/movie").mock(
        return_value=_pagina(1, 500, [1], 10000)
    )
    async with TMDBClient("tok") as cliente:
        resultados = await paginar(cliente, "/discover/movie", {}, max_paginas=3)

    assert len(resultados) == 3


@respx.mock
async def test_descobrir_fatiado_divide_quando_estoura_o_teto():
    # A primeira sondagem devolve mais que o teto, forçando a divisão em duas
    # metades; cada metade cabe e é paginada normalmente.
    chamadas: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        chamadas.append(params)
        inicio = params.get("primary_release_date.gte", "")
        fim = params.get("primary_release_date.lte", "")

        if inicio == "2000-01-01" and fim == "2001-12-31":
            return _pagina(1, 1, [], 12000)
        if inicio == "2000-01-01":
            return _pagina(1, 1, [10], 1)
        return _pagina(1, 1, [20], 1)

    respx.get("https://api.themoviedb.org/3/discover/movie").mock(side_effect=responder)

    async with TMDBClient("tok") as cliente:
        resultados = await descobrir_fatiado(
            cliente, {}, ano_inicial=2000, ano_final=2001
        )

    assert sorted(r["id"] for r in resultados) == [10, 20]
    assert len(chamadas) >= 3

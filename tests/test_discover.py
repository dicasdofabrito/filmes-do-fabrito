import httpx
import pytest
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


@respx.mock
async def test_descobrir_fatiado_um_ano_excedendo_teto_subdivide_por_data():
    """Um ano inteiro que excede o teto é subdividido em intervalos menores."""
    chamadas: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        chamadas.append(params)
        inicio = params.get("primary_release_date.gte", "")
        fim = params.get("primary_release_date.lte", "")

        # Ano completo (2005-01-01 a 2005-12-31) excede o teto
        if inicio == "2005-01-01" and fim == "2005-12-31":
            return _pagina(1, 1, [], 12000)

        # Qualquer intervalo menor que um ano completo cabe (retorna 1000 resultados)
        # Usa IDs diferentes por primeira data para verificar recursão
        if inicio.startswith("2005"):
            id_base = int(inicio[5:7]) * 100 + int(inicio[8:10])
            return _pagina(1, 1, [id_base], 1000)

        # Fallback para outras datas
        return _pagina(1, 1, [], 0)

    respx.get("https://api.themoviedb.org/3/discover/movie").mock(side_effect=responder)

    async with TMDBClient("tok") as cliente:
        resultados = await descobrir_fatiado(
            cliente, {}, ano_inicial=2005, ano_final=2005
        )

    # Verifica que pelo menos um request foi feito com intervalo mais estreito
    # que um ano completo
    tem_intervalo_estreito = any(
        (req.get("primary_release_date.gte", "").startswith("2005")
         and req.get("primary_release_date.lte", "").startswith("2005")
         and not (req.get("primary_release_date.gte") == "2005-01-01"
                  and req.get("primary_release_date.lte") == "2005-12-31"))
        for req in chamadas
    )
    assert tem_intervalo_estreito, "Deve haver pelo menos um intervalo mais estreito que o ano"

    # Verifica que resultados foram recuperados (não vazio)
    assert len(resultados) > 0, "Deve ter recuperado resultados das subfaixas"


@respx.mock
async def test_descobrir_fatiado_piso_um_dia_excedendo_teto_emite_aviso(caplog):
    """Um dia que excede o teto emite aviso e retorna (não levanta)."""

    def responder(request: httpx.Request) -> httpx.Response:
        # Simula um cenário patológico: TODOS os intervalos excedem o teto,
        # inclusive um único dia. Força a recursão até o piso e o aviso.
        # Retorna 500 resultados (página 1 tem 500, total_results > cap)
        return _pagina(1, 1, list(range(1, 501)), 11000)

    respx.get("https://api.themoviedb.org/3/discover/movie").mock(side_effect=responder)

    with caplog.at_level("WARNING"):
        async with TMDBClient("tok") as cliente:
            resultados = await descobrir_fatiado(
                cliente, {}, ano_inicial=2010, ano_final=2010
            )

    # Não deve levantar exceção
    assert resultados is not None

    # Deve ter emitido um aviso sobre um dia que excede o teto
    warning_msgs = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert len(warning_msgs) > 0, f"Deve haver ao menos um aviso. Avisos capturados: {warning_msgs}"
    assert any("excedendo" in msg.lower() or "2010" in msg for msg in warning_msgs), \
        f"Deve haver um aviso sobre exced�ncia ou a data. Avisos: {warning_msgs}"

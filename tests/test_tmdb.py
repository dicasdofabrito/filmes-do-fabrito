import httpx
import pytest
import respx

from sync.tmdb import TMDBClient, TMDBError


@respx.mock
async def test_get_envia_o_token_como_bearer():
    rota = respx.get("https://api.themoviedb.org/3/movie/603").mock(
        return_value=httpx.Response(200, json={"id": 603})
    )
    async with TMDBClient("tok_abc") as cliente:
        dados = await cliente.get("/movie/603")

    assert dados == {"id": 603}
    assert rota.calls.last.request.headers["authorization"] == "Bearer tok_abc"


@respx.mock
async def test_get_repete_apos_429_e_devolve_o_sucesso():
    respx.get("https://api.themoviedb.org/3/movie/603").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"id": 603}),
        ]
    )
    async with TMDBClient("tok", backoff_base=0.0) as cliente:
        assert await cliente.get("/movie/603") == {"id": 603}


@respx.mock
async def test_get_desiste_apos_esgotar_as_tentativas():
    respx.get("https://api.themoviedb.org/3/movie/603").mock(
        return_value=httpx.Response(503)
    )
    async with TMDBClient("tok", max_retries=3, backoff_base=0.0) as cliente:
        with pytest.raises(TMDBError, match="3 tentativas"):
            await cliente.get("/movie/603")


@respx.mock
async def test_get_nao_repete_erro_definitivo():
    rota = respx.get("https://api.themoviedb.org/3/movie/1").mock(
        return_value=httpx.Response(404, json={"status_message": "Not found"})
    )
    async with TMDBClient("tok", backoff_base=0.0) as cliente:
        with pytest.raises(TMDBError, match="404"):
            await cliente.get("/movie/1")

    assert rota.call_count == 1

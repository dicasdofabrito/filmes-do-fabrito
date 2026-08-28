import gzip
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from sync.build import IndiceGrandeDemais
from sync.catalog import Movie, escrever_catalogo, ler_catalogo
from sync.cli import executar, publicar_atomico
from sync.enrich import buscar_detalhes
from sync.exports import url_export
from sync.tmdb import TMDBClient, TMDBError

CONFIG_BASE = {
    "admissao": {
        "min_votos_acervo": 50,
        "meses_recente": 18,
        "min_votos_recente": 5,
        "min_popularidade_recente": 8.0,
        "min_duracao": 60,
    },
    "motor": {
        "suavizacao_k": 2.0,
        "qualidade_m": 500,
        "peso_afinidade": 0.75,
        "min_avaliacoes": 10,
        "pesos": {
            "keyword": 0.40,
            "director": 0.20,
            "cast": 0.15,
            "genre": 0.15,
            "decade": 0.06,
            "language": 0.04,
        },
    },
    "build": {"limite_index_mb": 6.0, "tamanho_fileira": 24},
    "fileiras": [],
}


def _preparar_raiz(
    tmp_path: Path,
    *,
    catalogo: list[Movie] | None = None,
    perfil: dict | None = None,
    config: dict | None = None,
) -> Path:
    raiz = tmp_path
    (raiz / "data").mkdir(parents=True, exist_ok=True)
    (raiz / "config.json").write_text(
        json.dumps(config or CONFIG_BASE), encoding="utf-8"
    )
    (raiz / "data" / "vibes.json").write_text("{}", encoding="utf-8")
    if catalogo is not None:
        escrever_catalogo(raiz / "data" / "catalog.jsonl", catalogo)
    if perfil is not None:
        (raiz / "data" / "profile.json").write_text(
            json.dumps(perfil), encoding="utf-8"
        )
    return raiz


def _filme(
    id_: int,
    *,
    track: str,
    added: str,
    vote_count: int = 10,
    title: str = "Antigo",
) -> Movie:
    return Movie(
        id=id_,
        title=title,
        year=2020,
        runtime=100,
        genres=(),
        keywords=(),
        vote_average=7.0,
        vote_count=vote_count,
        directors=(),
        cast=(),
        language="en",
        track=track,
        theatrical=False,
        added=added,
    )


def _detalhe(
    id_: int,
    *,
    vote_count: int = 100,
    popularity: float = 50.0,
    runtime: int = 100,
    release_date: str = "2020-01-01",
    adult: bool = False,
) -> dict:
    return {
        "id": id_,
        "title": f"Filme {id_}",
        "original_title": f"Filme {id_}",
        "adult": adult,
        "runtime": runtime,
        "vote_count": vote_count,
        "vote_average": 7.0,
        "popularity": popularity,
        "release_date": release_date,
        "original_language": "en",
        "genres": [],
        "credits": {"cast": [], "crew": []},
        "keywords": {"keywords": []},
        "release_dates": {"results": []},
    }


def _mock_exports_sem_novidade(hoje: date) -> None:
    """Export de hoje e de ontem idênticos: nenhum id novo pelo caminho diário."""
    vazio = gzip.compress(b"")
    respx.get(url_export(hoje)).mock(return_value=httpx.Response(200, content=vazio))
    respx.get(url_export(hoje - timedelta(days=1))).mock(
        return_value=httpx.Response(200, content=vazio)
    )


@respx.mock
async def test_buscar_detalhes_pede_keywords_e_creditos():
    rota = respx.get(url__regex=r".*/movie/\d+").mock(
        return_value=httpx.Response(200, json={"id": 1})
    )
    async with TMDBClient("tok") as cliente:
        await buscar_detalhes(cliente, [1])

    params = dict(rota.calls.last.request.url.params)
    assert params["append_to_response"] == "keywords,credits,release_dates"
    assert params["language"] == "pt-BR"


@respx.mock
async def test_buscar_detalhes_propaga_falha_definitiva():
    respx.get(url__regex=r".*/movie/\d+").mock(return_value=httpx.Response(503))
    async with TMDBClient("tok", max_retries=2, backoff_base=0.0) as cliente:
        with pytest.raises(TMDBError):
            await buscar_detalhes(cliente, [1])


def test_publicar_atomico_substitui_o_conteudo(tmp_path):
    definitivo = tmp_path / "site" / "data"
    definitivo.mkdir(parents=True)
    (definitivo / "antigo.json").write_text("velho", encoding="utf-8")

    temporario = tmp_path / "tmp"
    temporario.mkdir()
    (temporario / "index.json").write_text("novo", encoding="utf-8")

    publicar_atomico(temporario, definitivo)

    assert (definitivo / "index.json").read_text(encoding="utf-8") == "novo"
    assert not (definitivo / "antigo.json").exists()


def test_publicar_atomico_cria_o_destino_se_nao_existir(tmp_path):
    temporario = tmp_path / "tmp"
    temporario.mkdir()
    (temporario / "index.json").write_text("novo", encoding="utf-8")

    destino = tmp_path / "nao" / "existe"
    publicar_atomico(temporario, destino)

    assert (destino / "index.json").read_text(encoding="utf-8") == "novo"


# ---------------------------------------------------------------------------
# Correção 1: a carga inicial faz duas varreduras, e só uma delas carrega o
# piso de votos.
# ---------------------------------------------------------------------------


@respx.mock
async def test_carga_inicial_aplica_piso_de_votos_so_na_varredura_de_acervo(
    tmp_path,
):
    chamadas: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        chamadas.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={"page": 1, "total_pages": 1, "total_results": 0, "results": []},
        )

    respx.get("https://api.themoviedb.org/3/discover/movie").mock(
        side_effect=responder
    )

    raiz = _preparar_raiz(tmp_path)
    hoje = date(2026, 8, 27)

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=True)

    assert chamadas, "esperava pelo menos uma chamada ao /discover/movie"

    varredura_acervo = [
        c for c in chamadas if c.get("primary_release_date.gte") == "1874-01-01"
    ]
    varredura_recente = [
        c for c in chamadas if c.get("primary_release_date.gte") != "1874-01-01"
    ]

    assert varredura_acervo
    assert all(c.get("vote_count.gte") == "50" for c in varredura_acervo)

    assert varredura_recente
    assert all("vote_count.gte" not in c for c in varredura_recente)


# ---------------------------------------------------------------------------
# Correção 2: a trilha "recente" é sempre reprocessada.
# ---------------------------------------------------------------------------


@respx.mock
async def test_lista_de_busca_inclui_filmes_da_trilha_recente_mesmo_sem_serem_novos(
    tmp_path,
):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [
        _filme(555, track="recente", added="2026-01-01", vote_count=10)
    ]
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil={"movies": {}})

    rota_detalhe = respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(
            200, json=_detalhe(555, vote_count=12, release_date="2026-06-01")
        )
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    assert rota_detalhe.called, (
        "filme já catalogado na trilha 'recente' deveria ser reprocessado, "
        "não só ids novos do export"
    )


@respx.mock
async def test_refresh_preserva_a_data_de_entrada_original(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [
        _filme(555, track="recente", added="2025-01-01", vote_count=10)
    ]
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil={"movies": {}})

    respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(
            200, json=_detalhe(555, vote_count=12, release_date="2026-06-01")
        )
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    catalogo_final = ler_catalogo(raiz / "data" / "catalog.jsonl")
    assert catalogo_final[555].added == "2025-01-01"


@respx.mock
async def test_refresh_com_votos_suficientes_gradua_para_acervo(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [
        _filme(555, track="recente", added="2025-01-01", vote_count=10)
    ]
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil={"movies": {}})

    respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(
            200, json=_detalhe(555, vote_count=200, release_date="2026-06-01")
        )
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    catalogo_final = ler_catalogo(raiz / "data" / "catalog.jsonl")
    assert catalogo_final[555].track == "acervo"


@respx.mock
async def test_refresh_rejeitado_e_removido_mas_protegido_permanece(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    # Os dois já passaram da janela do "recente" (mais de 18 meses desde o
    # lançamento) sem acumular votos suficientes: classificar() rejeita.
    catalogo_inicial = [
        _filme(555, track="recente", added="2025-01-01", vote_count=10, title="Livre"),
        _filme(
            777, track="recente", added="2025-01-01", vote_count=10, title="Protegido"
        ),
    ]
    raiz = _preparar_raiz(
        tmp_path,
        catalogo=catalogo_inicial,
        perfil={"movies": {"777": {"seen": True, "rating": 1, "want": False, "at": ""}}},
    )

    detalhe_rejeitado = _detalhe(0, vote_count=10, release_date="2015-01-01")
    respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(200, json={**detalhe_rejeitado, "id": 555})
    )
    respx.get("https://api.themoviedb.org/3/movie/777").mock(
        return_value=httpx.Response(200, json={**detalhe_rejeitado, "id": 777})
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    catalogo_final = ler_catalogo(raiz / "data" / "catalog.jsonl")
    assert 555 not in catalogo_final
    assert 777 in catalogo_final
    # O histórico do Fabio não é destruído: a entrada antiga é preservada tal
    # como estava, e não é sobrescrita pelos dados novos que a rejeitaram.
    assert catalogo_final[777].added == "2025-01-01"
    assert catalogo_final[777].track == "recente"


# ---------------------------------------------------------------------------
# Atomicidade: nada é publicado se uma etapa falhar depois que o catálogo já
# foi lido.
# ---------------------------------------------------------------------------


@respx.mock
async def test_nada_e_publicado_se_uma_etapa_falhar(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    config_com_limite_minusculo = {
        **CONFIG_BASE,
        "build": {"limite_index_mb": 1e-9, "tamanho_fileira": 24},
    }
    catalogo_inicial = [_filme(1, track="acervo", added="2020-01-01")]
    raiz = _preparar_raiz(
        tmp_path,
        catalogo=catalogo_inicial,
        perfil={"movies": {}},
        config=config_com_limite_minusculo,
    )

    destino_site = raiz / "site" / "data"
    destino_site.mkdir(parents=True)
    (destino_site / "antigo.json").write_text("velho", encoding="utf-8")

    conteudo_catalogo_antes = (raiz / "data" / "catalog.jsonl").read_text(
        encoding="utf-8"
    )

    with pytest.raises(IndiceGrandeDemais):
        await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    # O destino do site continua exatamente como estava.
    assert (destino_site / "antigo.json").read_text(encoding="utf-8") == "velho"
    assert not (destino_site / "index.json").exists()
    assert sorted(p.name for p in destino_site.iterdir()) == ["antigo.json"]

    # O catálogo em disco também não foi tocado.
    assert (
        raiz / "data" / "catalog.jsonl"
    ).read_text(encoding="utf-8") == conteudo_catalogo_antes

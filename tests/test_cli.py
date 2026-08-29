import gzip
import json
import logging
import tempfile
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
    theatrical: bool = False,
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
        theatrical=theatrical,
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
async def test_acervo_theatrical_e_reprocessado_e_perde_a_flag_ao_sair_em_casa(
    tmp_path,
):
    """Correção B1: um filme admitido como "acervo" com `theatrical=True`
    (lançamento amplo que já passou de 50 votos em poucos dias) não pode
    congelar na fileira "Nos cinemas" para sempre — precisa continuar sendo
    reprocessado até o lançamento digital aparecer em `release_dates`."""
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [
        _filme(
            555,
            track="acervo",
            added="2026-08-01",
            vote_count=200,
            theatrical=True,
        )
    ]
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil={"movies": {}})

    detalhe = _detalhe(555, vote_count=200, release_date="2026-08-01")
    detalhe["release_dates"] = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "2026-08-01T00:00:00.000Z"},
                    {"type": 4, "release_date": "2026-08-20T00:00:00.000Z"},
                ],
            }
        ]
    }
    rota_detalhe = respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(200, json=detalhe)
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    assert rota_detalhe.called, (
        "filme 'acervo' com theatrical=True deveria ser reprocessado, não "
        "só filmes da trilha 'recente'"
    )

    catalogo_final = ler_catalogo(raiz / "data" / "catalog.jsonl")
    assert catalogo_final[555].track == "acervo"
    assert catalogo_final[555].theatrical is False


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

    # O catálogo em disco também não foi tocado (o conteúdo é idêntico ao
    # que já estava, então a reescrita não muda o texto).
    assert (
        raiz / "data" / "catalog.jsonl"
    ).read_text(encoding="utf-8") == conteudo_catalogo_antes

    # B7: nenhum diretório temporário "fdf-*" ficou órfão dentro de `raiz`
    # (mkdtemp usa dir=raiz para garantir mesmo sistema de arquivos do
    # destino — ver publicar_atomico).
    assert list(raiz.glob("fdf-*")) == []


# ---------------------------------------------------------------------------
# Fix round 1 — CRÍTICO 1: publicar_atomico por rename-aside, com autocura.
# ---------------------------------------------------------------------------


def test_publicar_atomico_autocura_apos_travar_entre_backup_e_troca(tmp_path):
    site = tmp_path / "site"
    site.mkdir()

    # Uma rodada anterior travou depois de mover o destino para o backup,
    # mas antes de mover o novo conteúdo para o lugar: o backup existe, o
    # destino não.
    backup = site / ".data-anterior"
    backup.mkdir()
    (backup / "antigo.json").write_text("velho", encoding="utf-8")

    definitivo = site / "data"
    assert not definitivo.exists()

    temporario = tmp_path / "tmp"
    temporario.mkdir()
    (temporario / "index.json").write_text("novo", encoding="utf-8")

    publicar_atomico(temporario, definitivo)

    # A rodada travada se autocurou e a publicação desta rodada completou
    # normalmente: nada explodiu por o destino ter sumido, e o backup foi
    # descartado depois de servir para a autocura.
    assert (definitivo / "index.json").read_text(encoding="utf-8") == "novo"
    assert not backup.exists()


def test_publicar_atomico_autocura_com_backup_e_destino_presentes(tmp_path):
    # Uma rodada anterior travou depois do último passo (destino já
    # trocado, backup ainda não removido): as duas pastas coexistem.
    site = tmp_path / "site"
    site.mkdir()

    backup = site / ".data-anterior"
    backup.mkdir()
    (backup / "antigo.json").write_text("bem_velho", encoding="utf-8")

    definitivo = site / "data"
    definitivo.mkdir()
    (definitivo / "index.json").write_text("velho", encoding="utf-8")

    temporario = tmp_path / "tmp"
    temporario.mkdir()
    (temporario / "index.json").write_text("novo", encoding="utf-8")

    publicar_atomico(temporario, definitivo)

    assert (definitivo / "index.json").read_text(encoding="utf-8") == "novo"
    assert not backup.exists()


# ---------------------------------------------------------------------------
# Fix round 1 — CRÍTICO 2: catálogo escrito por arquivo temporário +
# os.replace, sem nenhuma etapa arriscada entre as duas publicações.
# ---------------------------------------------------------------------------


@respx.mock
async def test_falha_ao_escrever_o_catalogo_temporario_preserva_o_arquivo_original(
    tmp_path, monkeypatch
):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [_filme(1, track="acervo", added="2020-01-01")]
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil={"movies": {}})

    destino_site = raiz / "site" / "data"
    destino_site.mkdir(parents=True)
    (destino_site / "antigo.json").write_text("velho", encoding="utf-8")

    conteudo_catalogo_antes = (raiz / "data" / "catalog.jsonl").read_text(
        encoding="utf-8"
    )

    def _explode(*_args, **_kwargs):
        raise RuntimeError("falha simulada ao gravar o catálogo")

    monkeypatch.setattr("sync.cli.escrever_catalogo", _explode)

    diretorios_temp_antes = set(Path(tempfile.gettempdir()).glob("fdf-*"))

    with pytest.raises(RuntimeError):
        await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    # O catálogo definitivo não foi tocado: a escrita falhou no arquivo
    # temporário, antes do os.replace.
    assert (
        raiz / "data" / "catalog.jsonl"
    ).read_text(encoding="utf-8") == conteudo_catalogo_antes
    # O site também não foi publicado — a falha aconteceu antes do
    # publicar_atomico.
    assert (destino_site / "antigo.json").read_text(encoding="utf-8") == "velho"
    assert not (destino_site / "index.json").exists()
    # B2: nomes.json e tmdb_ids_ontem.json.gz também ficam intocados — eles
    # entram na mesma seção atômica do catálogo, depois do os.replace que
    # nunca chegou a acontecer.
    assert not (raiz / "data" / "nomes.json").exists()
    assert not (raiz / "data" / "tmdb_ids_ontem.json.gz").exists()
    # IMPORTANTE 5: nenhum diretório temporário ficou órfão.
    diretorios_temp_depois = set(Path(tempfile.gettempdir()).glob("fdf-*"))
    assert diretorios_temp_depois == diretorios_temp_antes


# ---------------------------------------------------------------------------
# Fix round 1 — IMPORTANTE 3: um filme removido do TMDB (404/410) sai do
# catálogo sem derrubar a rodada; qualquer outro erro continua abortando.
# ---------------------------------------------------------------------------


@respx.mock
async def test_filme_removido_do_tmdb_sai_do_catalogo_e_a_rodada_publica(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [
        _filme(555, track="recente", added="2025-01-01", vote_count=10),
        _filme(1, track="acervo", added="2020-01-01"),
    ]
    perfil = {
        "movies": {"555": {"seen": True, "rating": 1, "want": False, "at": ""}}
    }
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil=perfil)

    conteudo_perfil_antes = (raiz / "data" / "profile.json").read_text(
        encoding="utf-8"
    )

    respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(404, json={"status_message": "not found"})
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    catalogo_final = ler_catalogo(raiz / "data" / "catalog.jsonl")
    assert 555 not in catalogo_final
    assert 1 in catalogo_final

    # O registro em profile.json não é tocado — vira um órfão, mas
    # continua lá, como o spec exige.
    assert (
        raiz / "data" / "profile.json"
    ).read_text(encoding="utf-8") == conteudo_perfil_antes

    # A rodada publicou normalmente apesar do 404.
    assert (raiz / "site" / "data" / "index.json").exists()


@respx.mock
async def test_erro_503_em_um_id_ainda_aborta_a_rodada_inteira(tmp_path, monkeypatch):
    async def _sem_espera(*_args, **_kwargs):
        return None

    # Só remove a espera do backoff — o comportamento de retry e a decisão
    # de propagar continuam sendo os de verdade do TMDBClient.
    monkeypatch.setattr("sync.tmdb.asyncio.sleep", _sem_espera)

    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    catalogo_inicial = [
        _filme(555, track="recente", added="2025-01-01", vote_count=10)
    ]
    raiz = _preparar_raiz(tmp_path, catalogo=catalogo_inicial, perfil={"movies": {}})

    destino_site = raiz / "site" / "data"
    destino_site.mkdir(parents=True)
    (destino_site / "antigo.json").write_text("velho", encoding="utf-8")

    respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(TMDBError):
        await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    assert (destino_site / "antigo.json").read_text(encoding="utf-8") == "velho"
    assert not (destino_site / "index.json").exists()


# ---------------------------------------------------------------------------
# Fix round 1 — IMPORTANTE 4: nomes de diretor/elenco persistem entre
# rodadas em data/nomes.json, mesclando em vez de substituir.
# ---------------------------------------------------------------------------


@respx.mock
async def test_nomes_persistidos_sao_mesclados_entre_execucoes(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    raiz = _preparar_raiz(
        tmp_path,
        catalogo=[
            _filme(1, track="acervo", added="2020-01-01"),
            _filme(555, track="recente", added="2026-01-01", vote_count=10),
        ],
        perfil={"movies": {}},
    )

    # Nome aprendido numa rodada anterior, de um filme que não será
    # reprocessado nesta rodada (é "acervo").
    (raiz / "data" / "nomes.json").write_text(
        json.dumps({"director": {"900": "Diretor Antigo"}, "cast": {}}),
        encoding="utf-8",
    )

    detalhe_555 = _detalhe(555, vote_count=12, release_date="2026-06-01")
    detalhe_555["credits"] = {
        "crew": [{"id": 42, "job": "Director", "name": "Diretor Novo"}],
        "cast": [],
    }
    respx.get("https://api.themoviedb.org/3/movie/555").mock(
        return_value=httpx.Response(200, json=detalhe_555)
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    nomes_final = json.loads(
        (raiz / "data" / "nomes.json").read_text(encoding="utf-8")
    )
    # O nome antigo sobreviveu — a rodada não refez o filme 1 e mesmo assim
    # não apagou o que já sabia sobre ele.
    assert nomes_final["director"]["900"] == "Diretor Antigo"
    # O nome novo, aprendido nesta rodada, entrou.
    assert nomes_final["director"]["42"] == "Diretor Novo"


# ---------------------------------------------------------------------------
# Fix wave final — B4: tmdb_ids_ontem.json.gz é gravado comprimido, com o
# nome exato do spec.
# ---------------------------------------------------------------------------


@respx.mock
async def test_ids_ontem_e_gravado_comprimido_com_o_nome_do_spec(tmp_path):
    hoje = date(2026, 8, 27)

    export_hoje = gzip.compress(
        b"\n".join(json.dumps({"id": i}).encode() for i in (1, 2, 3))
    )
    export_ontem = gzip.compress(
        b"\n".join(json.dumps({"id": i}).encode() for i in (1, 2))
    )
    respx.get(url_export(hoje)).mock(
        return_value=httpx.Response(200, content=export_hoje)
    )
    respx.get(url_export(hoje - timedelta(days=1))).mock(
        return_value=httpx.Response(200, content=export_ontem)
    )

    raiz = _preparar_raiz(tmp_path, perfil={"movies": {}})

    respx.get("https://api.themoviedb.org/3/movie/3").mock(
        return_value=httpx.Response(
            200, json=_detalhe(3, vote_count=0, popularity=0.0)
        )
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    caminho = raiz / "data" / "tmdb_ids_ontem.json.gz"
    assert caminho.exists()
    assert not (raiz / "data" / "tmdb_ids_ontem.json").exists()

    with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
        assert json.load(arquivo) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Fix wave final — B5: vibes.json ausente degrada, não derruba o build.
# ---------------------------------------------------------------------------


@respx.mock
async def test_vibes_ausente_nao_derruba_o_build(tmp_path, caplog):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    config_so_vibe = {**CONFIG_BASE, "fileiras": ["vibe"]}
    catalogo_inicial = [_filme(1, track="acervo", added="2020-01-01")]
    raiz = _preparar_raiz(
        tmp_path,
        catalogo=catalogo_inicial,
        perfil={"movies": {}},
        config=config_so_vibe,
    )
    # _preparar_raiz sempre cria vibes.json — removido de propósito para
    # simular a ausência do arquivo.
    (raiz / "data" / "vibes.json").unlink()

    with caplog.at_level(logging.WARNING, logger="sync.cli"):
        await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    assert "vibes.json ausente" in caplog.text

    dados = json.loads(
        (raiz / "site" / "data" / "shelves.json").read_text(encoding="utf-8")
    )
    # A fileira "vibe" simplesmente não aparece — o build não é abortado.
    assert dados["shelves"] == []


# ---------------------------------------------------------------------------
# IMPORTANTE 4.5: nomes de keyword também persistem em data/nomes.json,
# junto com director e cast.
# ---------------------------------------------------------------------------


@respx.mock
async def test_nomes_de_keyword_sao_persistidos(tmp_path):
    hoje = date(2026, 8, 27)
    _mock_exports_sem_novidade(hoje)

    raiz = _preparar_raiz(
        tmp_path,
        catalogo=[_filme(42, track="recente", added="2026-08-01", vote_count=10)],
        perfil={"movies": {}},
    )

    detalhe_42 = _detalhe(42, vote_count=12, release_date="2026-06-01")
    detalhe_42["keywords"] = {"keywords": [{"id": 900, "name": "vinganca"}]}
    respx.get("https://api.themoviedb.org/3/movie/42").mock(
        return_value=httpx.Response(200, json=detalhe_42)
    )

    await executar(raiz=raiz, token="tok", hoje=hoje, carga_inicial=False)

    nomes = json.loads((raiz / "data" / "nomes.json").read_text(encoding="utf-8"))
    assert nomes["keyword"]["900"] == "vinganca"

# Filmes do Fabrito — Plano 1: Pipeline de dados e motor de recomendação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o pipeline Python que baixa o catálogo do TMDB, aprende o gosto do Fabio a partir das avaliações dele e gera os arquivos JSON que o site consumirá.

**Architecture:** Um pacote Python `sync/` com responsabilidade única por módulo, orquestrado por um CLI. O cliente HTTP é isolado do resto para que toda a lógica de negócio seja testável sem rede. O motor de pontuação é puro — recebe catálogo e perfil, devolve números — e por isso concentra os testes. A escrita final é atômica: tudo é montado em diretório temporário e só é movido para o lugar definitivo quando todas as etapas passam.

**Tech Stack:** Python 3.12, `httpx` (async), `pytest`, `pytest-asyncio`, `respx` (mock de HTTP).

**Spec:** `docs/superpowers/specs/2026-08-27-filmes-do-fabrito-design.md`

**Escopo deste plano:** etapas 1 a 3 da ordem de construção do spec (seção 13). O site, a escrita do perfil pelo navegador e a automação do GitHub Actions ficam para o Plano 2, que consome os arquivos produzidos aqui.

## Global Constraints

- Python 3.12. Sem framework web neste plano.
- Autenticação no TMDB pelo **v4 Read Access Token**, header `Authorization: Bearer <token>`, lido da variável de ambiente `TMDB_TOKEN`. Nunca em arquivo commitado, nunca em parâmetro de URL.
- Idioma das requisições ao TMDB: `language=pt-BR`, `region=BR`.
- **Idioma do código:** identificadores de domínio em português (`classificar`,
  `montar_filme`, `descobrir_fatiado`, variáveis locais). O inglês é preservado
  em dois lugares, e só neles: nos campos do dataclass `Movie`, que espelham o
  contrato JSON consumido pelo site, e onde o nome reproduz um campo da API do
  TMDB (`vote_count`, `release_date`). Comentários, docstrings e mensagens de
  commit em português.
- O catálogo é `data/catalog.jsonl`, **uma linha por filme, ordenado por `id` crescente**. A ordenação é requisito, não estilo: é o que permite ao git guardar só o delta diário.
- Nenhuma etapa do pipeline escreve direto em `data/` ou `site/data/`. Tudo passa por diretório temporário e é movido no fim. Falhou, não move nada.
- Cortes de admissão comuns às duas trilhas: `adult = false`, `runtime >= 60`.
- Pesos do motor, imutáveis sem nova decisão: keyword 0,40 · diretor 0,20 · elenco 0,15 · gênero 0,15 · década 0,06 · idioma 0,04.
- Nenhum teste pode depender da API do TMDB estar no ar. Respostas reais viram fixtures em `tests/fixtures/`.

---

### Task 1: Fundação do projeto e cliente TMDB

Estabelece o pacote, as dependências e a única peça que fala com a rede. Todo o resto do pipeline é código puro que consome o que este módulo devolve.

**Files:**
- Create: `pyproject.toml`
- Create: `sync/__init__.py`
- Create: `sync/tmdb.py`
- Create: `tests/__init__.py`
- Create: `tests/test_tmdb.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `class TMDBError(RuntimeError)`
  - `class TMDBClient` com `__init__(self, token: str, *, base_url: str = BASE_URL, max_retries: int = 5, backoff_base: float = 0.5)`, uso como context manager assíncrono, e `async def get(self, path: str, **params) -> dict`.

- [ ] **Step 1: Criar `pyproject.toml`**

```toml
[project]
name = "filmes-do-fabrito"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "respx>=0.21"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["sync*"]
```

- [ ] **Step 2: Criar os arquivos vazios de pacote e instalar**

```bash
mkdir -p sync tests tests/fixtures
touch sync/__init__.py tests/__init__.py
printf '.venv/\nsite/data/\n' >> .gitignore
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
```

- [ ] **Step 3: Escrever os testes que falham**

Crie `tests/test_tmdb.py`:

```python
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
```

- [ ] **Step 4: Rodar os testes e confirmar que falham**

Run: `.venv/Scripts/pytest tests/test_tmdb.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.tmdb'`

- [ ] **Step 5: Implementar `sync/tmdb.py`**

```python
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
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_tmdb.py -v`
Expected: PASS, 4 testes

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml sync tests .gitignore
git commit -m "feat: cliente TMDB com retry e backoff"
```

---

### Task 2: Paginação e fatiamento por ano

O `/discover` para em 500 páginas (10.000 resultados). Consultas amplas estouram esse teto e precisam ser fatiadas por ano de lançamento até cada fatia caber. Sem isso a carga inicial silenciosamente perde dezenas de milhares de filmes.

**Files:**
- Create: `sync/discover.py`
- Create: `tests/test_discover.py`

**Interfaces:**
- Consumes: `TMDBClient.get` da Task 1.
- Produces:
  - `TETO_DISCOVER: int = 10_000`
  - `async def paginar(cliente: TMDBClient, path: str, params: dict, *, max_paginas: int = 500) -> list[dict]`
  - `async def descobrir_fatiado(cliente: TMDBClient, params: dict, *, ano_inicial: int = 1874, ano_final: int) -> list[dict]`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_discover.py`:

```python
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
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_discover.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.discover'`

- [ ] **Step 3: Implementar `sync/discover.py`**

```python
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
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_discover.py -v`
Expected: PASS, 3 testes

- [ ] **Step 5: Commit**

```bash
git add sync/discover.py tests/test_discover.py
git commit -m "feat: paginacao e fatiamento por ano do discover"
```

---

### Task 3: Export diário de IDs

O TMDB publica todo dia um arquivo com todos os ids de filmes do acervo. Comparar o de hoje com o de ontem revela os ids novos sem varrer a API inteira — é o que faz o sync diário levar segundos em vez de minutos.

**Files:**
- Create: `sync/exports.py`
- Create: `tests/test_exports.py`

**Interfaces:**
- Consumes: nada da Task 1 (o arquivo fica em `files.tmdb.org` e não pede autenticação).
- Produces:
  - `def url_export(dia: date) -> str`
  - `async def baixar_export(dia: date, *, client: httpx.AsyncClient | None = None) -> set[int]`
  - `def ids_novos(hoje: set[int], ontem: set[int]) -> set[int]`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_exports.py`:

```python
import gzip
import json
from datetime import date

import httpx
import respx

from sync.exports import baixar_export, ids_novos, url_export


def test_url_export_usa_o_formato_mes_dia_ano():
    assert url_export(date(2026, 8, 27)) == (
        "http://files.tmdb.org/p/exports/movie_ids_08_27_2026.json.gz"
    )


@respx.mock
async def test_baixar_export_le_jsonl_comprimido():
    linhas = b"\n".join(
        json.dumps({"id": i, "original_title": f"F{i}"}).encode() for i in (1, 2, 3)
    )
    respx.get(url_export(date(2026, 8, 27))).mock(
        return_value=httpx.Response(200, content=gzip.compress(linhas))
    )

    assert await baixar_export(date(2026, 8, 27)) == {1, 2, 3}


def test_ids_novos_devolve_apenas_a_diferenca():
    assert ids_novos({1, 2, 3}, {1, 2}) == {3}
    assert ids_novos({1}, {1, 2}) == set()
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_exports.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.exports'`

- [ ] **Step 3: Implementar `sync/exports.py`**

```python
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
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_exports.py -v`
Expected: PASS, 3 testes

- [ ] **Step 5: Commit**

```bash
git add sync/exports.py tests/test_exports.py
git commit -m "feat: leitura do export diario de ids do TMDB"
```

---

### Task 4: Configuração e regras de admissão

Traz o `config.json` (primeiro ponto onde parâmetros são necessários) e as duas trilhas de admissão. A regra da trilha *Recente* existe porque um filme lançado ontem tem 3 votos e seria excluído por qualquer limiar de consenso.

**Files:**
- Create: `config.json`
- Create: `sync/config.py`
- Create: `sync/admission.py`
- Create: `tests/test_admission.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `@dataclass(frozen=True) class Config` com atributos `admissao: Admissao`, `motor: Motor`, `build: Build`, `fileiras: tuple[str, ...]`
  - `@dataclass(frozen=True) class Admissao` com `min_votos_acervo: int`, `meses_recente: int`, `min_votos_recente: int`, `min_popularidade_recente: float`, `min_duracao: int`
  - `@dataclass(frozen=True) class Motor` com `suavizacao_k: float`, `qualidade_m: int`, `peso_afinidade: float`, `min_avaliacoes: int`, `pesos: dict[str, float]` — nesta ordem: as Tasks 8 e 9 constroem `Motor(...)` posicionalmente nos testes
  - `@dataclass(frozen=True) class Build` com `limite_index_mb: float`, `tamanho_fileira: int`
  - `def carregar_config(caminho: Path) -> Config`
  - `def classificar(detalhe: dict, hoje: date, cfg: Admissao) -> str | None` devolvendo `"acervo"`, `"recente"` ou `None`

- [ ] **Step 1: Criar `config.json`**

```json
{
  "admissao": {
    "min_votos_acervo": 50,
    "meses_recente": 18,
    "min_votos_recente": 5,
    "min_popularidade_recente": 8.0,
    "min_duracao": 60
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
      "language": 0.04
    }
  },
  "build": {
    "limite_index_mb": 6.0,
    "tamanho_fileira": 24
  },
  "fileiras": [
    "watchlist",
    "novos",
    "similar",
    "vibe",
    "diretor",
    "ator",
    "curto",
    "classicos",
    "aposta",
    "ponto_cego",
    "cinemas"
  ]
}
```

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_admission.py`:

```python
import json
from datetime import date
from pathlib import Path

from sync.admission import classificar
from sync.config import carregar_config

HOJE = date(2026, 8, 27)


def _cfg():
    return carregar_config(Path("config.json")).admissao


def _detalhe(**extras) -> dict:
    base = {
        "id": 1,
        "adult": False,
        "runtime": 120,
        "vote_count": 0,
        "popularity": 0.0,
        "release_date": "1999-03-31",
    }
    return {**base, **extras}


def test_config_carrega_os_pesos_do_motor():
    motor = carregar_config(Path("config.json")).motor
    assert motor.pesos["keyword"] == 0.40
    assert sum(motor.pesos.values()) == 1.0


def test_filme_com_muitos_votos_entra_no_acervo():
    assert classificar(_detalhe(vote_count=50), HOJE, _cfg()) == "acervo"


def test_filme_com_poucos_votos_e_antigo_fica_de_fora():
    assert classificar(_detalhe(vote_count=49), HOJE, _cfg()) is None


def test_lancamento_recente_com_poucos_votos_entra_como_recente():
    recente = _detalhe(vote_count=5, release_date="2026-08-01")
    assert classificar(recente, HOJE, _cfg()) == "recente"


def test_lancamento_recente_entra_por_popularidade_sem_votos():
    recente = _detalhe(vote_count=0, popularity=25.0, release_date="2026-08-01")
    assert classificar(recente, HOJE, _cfg()) == "recente"


def test_lancamento_recente_sem_votos_nem_popularidade_fica_de_fora():
    recente = _detalhe(vote_count=0, popularity=0.5, release_date="2026-08-01")
    assert classificar(recente, HOJE, _cfg()) is None


def test_curta_metragem_nunca_entra():
    curta = _detalhe(vote_count=9999, runtime=40)
    assert classificar(curta, HOJE, _cfg()) is None


def test_adulto_nunca_entra():
    assert classificar(_detalhe(vote_count=9999, adult=True), HOJE, _cfg()) is None


def test_sem_data_de_lancamento_so_pode_entrar_pelo_acervo():
    assert classificar(_detalhe(vote_count=50, release_date=""), HOJE, _cfg()) == "acervo"
    assert classificar(_detalhe(vote_count=5, release_date=""), HOJE, _cfg()) is None


def test_acervo_tem_prioridade_sobre_recente():
    # Um lançamento que já explodiu de votos é acervo, não recente: ele não
    # deve expirar em 18 meses.
    campeao = _detalhe(vote_count=5000, release_date="2026-08-01")
    assert classificar(campeao, HOJE, _cfg()) == "acervo"


def test_runtime_ausente_e_tratado_como_zero():
    assert classificar(_detalhe(vote_count=9999, runtime=None), HOJE, _cfg()) is None
```

- [ ] **Step 3: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_admission.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.config'`

- [ ] **Step 4: Implementar `sync/config.py`**

```python
"""Leitura tipada do config.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Admissao:
    min_votos_acervo: int
    meses_recente: int
    min_votos_recente: int
    min_popularidade_recente: float
    min_duracao: int


@dataclass(frozen=True)
class Motor:
    suavizacao_k: float
    qualidade_m: int
    peso_afinidade: float
    min_avaliacoes: int
    pesos: dict[str, float]


@dataclass(frozen=True)
class Build:
    limite_index_mb: float
    tamanho_fileira: int


@dataclass(frozen=True)
class Config:
    admissao: Admissao
    motor: Motor
    build: Build
    fileiras: tuple[str, ...]


def carregar_config(caminho: Path) -> Config:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Config(
        admissao=Admissao(**bruto["admissao"]),
        motor=Motor(**bruto["motor"]),
        build=Build(**bruto["build"]),
        fileiras=tuple(bruto["fileiras"]),
    )
```

- [ ] **Step 5: Implementar `sync/admission.py`**

```python
"""Regras de entrada no catálogo, em duas trilhas."""

from __future__ import annotations

from datetime import date

from sync.config import Admissao

ACERVO = "acervo"
RECENTE = "recente"


def _data_de(detalhe: dict) -> date | None:
    bruto = detalhe.get("release_date") or ""
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def classificar(detalhe: dict, hoje: date, cfg: Admissao) -> str | None:
    """Decide a trilha de admissão de um filme, ou None se ele não entra."""
    if detalhe.get("adult"):
        return None

    if (detalhe.get("runtime") or 0) < cfg.min_duracao:
        return None

    # Consenso acumulado tem prioridade: um lançamento que já explodiu de
    # votos entra como acervo e não expira depois de 18 meses.
    if detalhe.get("vote_count", 0) >= cfg.min_votos_acervo:
        return ACERVO

    lancamento = _data_de(detalhe)
    if lancamento is None:
        return None

    dias_de_vida = (hoje - lancamento).days
    if not 0 <= dias_de_vida <= cfg.meses_recente * 30:
        return None

    tem_votos = detalhe.get("vote_count", 0) >= cfg.min_votos_recente
    tem_tracao = detalhe.get("popularity", 0.0) >= cfg.min_popularidade_recente
    return RECENTE if (tem_votos or tem_tracao) else None
```

- [ ] **Step 6: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_admission.py -v`
Expected: PASS, 11 testes

- [ ] **Step 7: Commit**

```bash
git add config.json sync/config.py sync/admission.py tests/test_admission.py
git commit -m "feat: config tipada e regras de admissao em duas trilhas"
```

---

### Task 5: Classificação "nos cinemas"

Distingue o que o Fabio pode ver em casa do que ainda está só em sala. A regra vem do endpoint `release_dates`, não do `now_playing` — o segundo lista títulos em cartaz sem dizer se já saíram em casa, que é exatamente a informação que importa.

**Files:**
- Create: `sync/theatrical.py`
- Create: `tests/fixtures/release_dates_em_cartaz.json`
- Create: `tests/fixtures/release_dates_ja_lancado.json`
- Create: `tests/test_theatrical.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `TIPO_TEATRAL: int = 3`, `TIPOS_DOMESTICOS: frozenset[int] = frozenset({4, 5})`
  - `def apenas_no_cinema(release_dates: dict, hoje: date, *, regiao: str = "BR") -> bool`

- [ ] **Step 1: Criar as fixtures**

`tests/fixtures/release_dates_em_cartaz.json` — estreou em sala, sem lançamento doméstico:

```json
{
  "id": 1000,
  "results": [
    {
      "iso_3166_1": "BR",
      "release_dates": [
        {"type": 3, "release_date": "2026-08-14T00:00:00.000Z"}
      ]
    },
    {
      "iso_3166_1": "US",
      "release_dates": [
        {"type": 3, "release_date": "2026-08-01T00:00:00.000Z"}
      ]
    }
  ]
}
```

`tests/fixtures/release_dates_ja_lancado.json` — saiu em sala e já tem digital:

```json
{
  "id": 2000,
  "results": [
    {
      "iso_3166_1": "BR",
      "release_dates": [
        {"type": 3, "release_date": "2026-02-10T00:00:00.000Z"},
        {"type": 4, "release_date": "2026-05-20T00:00:00.000Z"}
      ]
    }
  ]
}
```

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_theatrical.py`:

```python
import json
from datetime import date
from pathlib import Path

from sync.theatrical import apenas_no_cinema

HOJE = date(2026, 8, 27)
FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def test_em_cartaz_sem_lancamento_domestico_e_apenas_cinema():
    assert apenas_no_cinema(_fixture("release_dates_em_cartaz.json"), HOJE) is True


def test_com_lancamento_digital_deixa_de_ser_apenas_cinema():
    assert apenas_no_cinema(_fixture("release_dates_ja_lancado.json"), HOJE) is False


def test_sem_estreia_no_brasil_nao_e_apenas_cinema():
    dados = {"results": [{"iso_3166_1": "US", "release_dates": [{"type": 3, "release_date": "2026-08-01T00:00:00.000Z"}]}]}
    assert apenas_no_cinema(dados, HOJE) is False


def test_estreia_futura_ainda_nao_conta_como_em_cartaz():
    dados = {"results": [{"iso_3166_1": "BR", "release_dates": [{"type": 3, "release_date": "2026-12-01T00:00:00.000Z"}]}]}
    assert apenas_no_cinema(dados, HOJE) is False


def test_digital_marcado_para_o_futuro_nao_tira_do_cinema():
    # Data de digital anunciada mas ainda não chegada: continua só no cinema.
    dados = {
        "results": [
            {
                "iso_3166_1": "BR",
                "release_dates": [
                    {"type": 3, "release_date": "2026-08-01T00:00:00.000Z"},
                    {"type": 4, "release_date": "2026-11-01T00:00:00.000Z"},
                ],
            }
        ]
    }
    assert apenas_no_cinema(dados, HOJE) is True


def test_resposta_vazia_nao_quebra():
    assert apenas_no_cinema({}, HOJE) is False
    assert apenas_no_cinema({"results": []}, HOJE) is False
```

- [ ] **Step 3: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_theatrical.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.theatrical'`

- [ ] **Step 4: Implementar `sync/theatrical.py`**

```python
"""Classificação 'só no cinema' a partir dos release_dates do TMDB."""

from __future__ import annotations

from datetime import date

# Tipos do TMDB: 1 premiere, 2 limitado, 3 teatral, 4 digital, 5 físico, 6 TV.
TIPO_TEATRAL = 3
TIPOS_DOMESTICOS = frozenset({4, 5})


def _data(entrada: dict) -> date | None:
    bruto = (entrada.get("release_date") or "")[:10]
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def apenas_no_cinema(
    release_dates: dict, hoje: date, *, regiao: str = "BR"
) -> bool:
    """True se o filme já estreou em sala no país e ainda não saiu em casa.

    Datas futuras são ignoradas nos dois lados: uma estreia anunciada ainda
    não é 'em cartaz', e um digital agendado ainda não é 'disponível'.
    """
    for pais in release_dates.get("results", []):
        if pais.get("iso_3166_1") != regiao:
            continue

        estreou = False
        saiu_em_casa = False

        for entrada in pais.get("release_dates", []):
            quando = _data(entrada)
            if quando is None or quando > hoje:
                continue
            if entrada.get("type") == TIPO_TEATRAL:
                estreou = True
            elif entrada.get("type") in TIPOS_DOMESTICOS:
                saiu_em_casa = True

        return estreou and not saiu_em_casa

    return False
```

- [ ] **Step 5: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_theatrical.py -v`
Expected: PASS, 6 testes

- [ ] **Step 6: Commit**

```bash
git add sync/theatrical.py tests/test_theatrical.py tests/fixtures
git commit -m "feat: classificacao de filmes apenas em cartaz no cinema"
```

---

### Task 6: Modelo do filme e persistência do catálogo

Define o registro que atravessa todo o pipeline e a leitura/escrita do JSONL. A ordenação por id é requisito de arquitetura: é o que faz o git guardar delta em vez de arquivo inteiro.

**Files:**
- Create: `sync/catalog.py`
- Create: `tests/test_catalog.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `@dataclass(frozen=True) class Movie` com campos `id: int`, `title: str`, `year: int | None`, `runtime: int`, `genres: tuple[int, ...]`, `keywords: tuple[int, ...]`, `vote_average: float`, `vote_count: int`, `directors: tuple[int, ...]`, `cast: tuple[int, ...]`, `language: str`, `track: str`, `theatrical: bool`, `added: str`
  - `Movie.to_row(self) -> dict` e `Movie.from_row(cls, row: dict) -> Movie`
  - `def ler_catalogo(caminho: Path) -> dict[int, Movie]`
  - `def escrever_catalogo(caminho: Path, filmes: Iterable[Movie]) -> None`
  - `def montar_filme(detalhe: dict, *, track: str, theatrical: bool, added: str) -> Movie`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_catalog.py`:

```python
from pathlib import Path

from sync.catalog import Movie, escrever_catalogo, ler_catalogo, montar_filme


def _filme(id_: int = 603, **extras) -> Movie:
    base = dict(
        id=id_,
        title="Matrix",
        year=1999,
        runtime=136,
        genres=(28, 878),
        keywords=(1701, 9743),
        vote_average=8.2,
        vote_count=25431,
        directors=(9339,),
        cast=(6384, 2975),
        language="en",
        track="acervo",
        theatrical=False,
        added="2026-08-27",
    )
    return Movie(**{**base, **extras})


def test_ida_e_volta_pela_linha_preserva_o_filme():
    original = _filme()
    assert Movie.from_row(original.to_row()) == original


def test_a_linha_usa_chaves_abreviadas():
    linha = _filme().to_row()
    assert linha["t"] == "Matrix"
    assert linha["k"] == [1701, 9743]
    assert "title" not in linha


def test_escrita_ordena_por_id(tmp_path: Path):
    destino = tmp_path / "catalog.jsonl"
    escrever_catalogo(destino, [_filme(300), _filme(100), _filme(200)])

    lidos = list(ler_catalogo(destino))
    assert lidos == [100, 200, 300]


def test_leitura_de_arquivo_inexistente_devolve_vazio(tmp_path: Path):
    assert ler_catalogo(tmp_path / "nao_existe.jsonl") == {}


def test_montar_filme_extrai_diretor_e_elenco_do_credits():
    detalhe = {
        "id": 603,
        "title": "Matrix",
        "release_date": "1999-03-31",
        "runtime": 136,
        "genres": [{"id": 28}, {"id": 878}],
        "keywords": {"keywords": [{"id": 1701}]},
        "vote_average": 8.2,
        "vote_count": 25431,
        "original_language": "en",
        "credits": {
            "cast": [{"id": i} for i in range(10)],
            "crew": [
                {"id": 9339, "job": "Director"},
                {"id": 111, "job": "Producer"},
            ],
        },
    }
    filme = montar_filme(detalhe, track="acervo", theatrical=False, added="2026-08-27")

    assert filme.directors == (9339,)
    assert filme.cast == (0, 1, 2, 3, 4)  # só os cinco primeiros
    assert filme.year == 1999
    assert filme.keywords == (1701,)


def test_montar_filme_tolera_campos_ausentes():
    filme = montar_filme(
        {"id": 7, "title": "X"}, track="recente", theatrical=True, added="2026-08-27"
    )
    assert filme.year is None
    assert filme.keywords == ()
    assert filme.directors == ()
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_catalog.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.catalog'`

- [ ] **Step 3: Implementar `sync/catalog.py`**

```python
"""Modelo do filme e persistência do catálogo em JSONL."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_ELENCO = 5


@dataclass(frozen=True)
class Movie:
    id: int
    title: str
    year: int | None
    runtime: int
    genres: tuple[int, ...]
    keywords: tuple[int, ...]
    vote_average: float
    vote_count: int
    directors: tuple[int, ...]
    cast: tuple[int, ...]
    language: str
    track: str
    theatrical: bool
    added: str

    def to_row(self) -> dict:
        """Serializa com chaves curtas — o arquivo tem dezenas de milhares
        de linhas e cada byte de nome de campo é multiplicado por isso."""
        return {
            "id": self.id,
            "t": self.title,
            "y": self.year,
            "r": self.runtime,
            "g": list(self.genres),
            "k": list(self.keywords),
            "v": self.vote_average,
            "n": self.vote_count,
            "d": list(self.directors),
            "c": list(self.cast),
            "l": self.language,
            "st": self.track,
            "th": self.theatrical,
            "a": self.added,
        }

    @classmethod
    def from_row(cls, row: dict) -> Movie:
        return cls(
            id=row["id"],
            title=row["t"],
            year=row["y"],
            runtime=row["r"],
            genres=tuple(row["g"]),
            keywords=tuple(row["k"]),
            vote_average=row["v"],
            vote_count=row["n"],
            directors=tuple(row["d"]),
            cast=tuple(row["c"]),
            language=row["l"],
            track=row["st"],
            theatrical=row["th"],
            added=row["a"],
        )


def montar_filme(
    detalhe: dict, *, track: str, theatrical: bool, added: str
) -> Movie:
    """Converte a resposta de /movie/{id} com append_to_response no modelo."""
    creditos = detalhe.get("credits") or {}
    equipe = creditos.get("crew") or []
    elenco = creditos.get("cast") or []
    palavras = (detalhe.get("keywords") or {}).get("keywords") or []
    lancamento = detalhe.get("release_date") or ""

    return Movie(
        id=detalhe["id"],
        title=detalhe.get("title") or detalhe.get("original_title") or "",
        year=int(lancamento[:4]) if lancamento[:4].isdigit() else None,
        runtime=detalhe.get("runtime") or 0,
        genres=tuple(g["id"] for g in detalhe.get("genres") or []),
        keywords=tuple(p["id"] for p in palavras),
        vote_average=detalhe.get("vote_average") or 0.0,
        vote_count=detalhe.get("vote_count") or 0,
        directors=tuple(p["id"] for p in equipe if p.get("job") == "Director"),
        cast=tuple(p["id"] for p in elenco[:MAX_ELENCO]),
        language=detalhe.get("original_language") or "",
        track=track,
        theatrical=theatrical,
        added=added,
    )


def ler_catalogo(caminho: Path) -> dict[int, Movie]:
    if not caminho.exists():
        return {}

    filmes: dict[int, Movie] = {}
    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                filme = Movie.from_row(json.loads(linha))
                filmes[filme.id] = filme
    return filmes


def escrever_catalogo(caminho: Path, filmes: Iterable[Movie]) -> None:
    """Grava ordenado por id. A ordem estável é o que permite ao git
    guardar apenas o delta diário em vez do arquivo inteiro."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        for filme in sorted(filmes, key=lambda f: f.id):
            arquivo.write(json.dumps(filme.to_row(), ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_catalog.py -v`
Expected: PASS, 6 testes

- [ ] **Step 5: Commit**

```bash
git add sync/catalog.py tests/test_catalog.py
git commit -m "feat: modelo do filme e persistencia do catalogo em jsonl"
```

---

### Task 7: Perfil e vetor de gosto

Lê as avaliações e transforma em pesos por característica. A normalização por raridade é o coração: sem ela `drama` domina o vetor, aparece em 40% do acervo e não informa nada.

**Files:**
- Create: `sync/profile.py`
- Create: `tests/test_profile.py`

**Interfaces:**
- Consumes: `Movie` da Task 6.
- Produces:
  - `@dataclass(frozen=True) class Entry` com `seen: bool`, `rating: int | None`, `want: bool`, `at: str`
  - `@dataclass(frozen=True) class Profile` com `movies: dict[int, Entry]` e os métodos `liked_ids()`, `disliked_ids()`, `seen_ids()`, `wanted_ids()`, todos devolvendo `set[int]`
  - `def ler_perfil(caminho: Path) -> Profile`
  - `def features_of(filme: Movie) -> dict[str, tuple]`
  - `@dataclass(frozen=True) class Taste` com `weights: dict[tuple[str, object], float]` e `n_ratings: int`
  - `def construir_gosto(perfil: Profile, catalogo: dict[int, Movie], *, k: float = 2.0) -> Taste`
  - `def gosto_de_um_filme(filme: Movie, catalogo: dict[int, Movie], *, k: float = 2.0) -> Taste`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_profile.py`:

```python
import json
import math
from pathlib import Path

import pytest

from sync.catalog import Movie
from sync.profile import (
    Entry,
    Profile,
    construir_gosto,
    features_of,
    gosto_de_um_filme,
    ler_perfil,
)


def _filme(id_: int, *, keywords=(), genres=(), directors=(), year=2000) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=100,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=7.0, vote_count=100,
        directors=tuple(directors), cast=(), language="en",
        track="acervo", theatrical=False, added="2026-08-27",
    )


def test_ler_perfil_separa_curtidos_rejeitados_e_watchlist(tmp_path: Path):
    caminho = tmp_path / "profile.json"
    caminho.write_text(
        json.dumps(
            {
                "movies": {
                    "1": {"seen": True, "rating": 1, "at": "2026-08-20"},
                    "2": {"seen": True, "rating": -1, "at": "2026-08-21"},
                    "3": {"seen": False, "want": True, "at": "2026-08-22"},
                }
            }
        ),
        encoding="utf-8",
    )
    perfil = ler_perfil(caminho)

    assert perfil.liked_ids() == {1}
    assert perfil.disliked_ids() == {2}
    assert perfil.seen_ids() == {1, 2}
    assert perfil.wanted_ids() == {3}


def test_ler_perfil_inexistente_devolve_perfil_vazio(tmp_path: Path):
    assert ler_perfil(tmp_path / "nada.json").movies == {}


def test_features_of_deriva_decada_do_ano():
    assert features_of(_filme(1, year=1999))["decade"] == (1990,)
    assert features_of(_filme(2, year=None))["decade"] == ()


def test_caracteristica_rara_pesa_mais_que_a_comum():
    # 'comum' está em todos os 10 filmes; 'rara' está só no curtido.
    catalogo = {i: _filme(i, keywords=(100,)) for i in range(1, 11)}
    catalogo[1] = _filme(1, keywords=(100, 200))

    perfil = Profile(movies={1: Entry(seen=True, rating=1, want=False, at="2026-08-20")})
    gosto = construir_gosto(perfil, catalogo)

    assert gosto.weights[("keyword", 200)] > gosto.weights[("keyword", 100)]


def test_caracteristica_presente_em_todo_o_catalogo_tem_peso_nulo():
    # idf = log(N / (1+N)) fica negativo por muito pouco; o teste garante que
    # uma característica onipresente não vira sinal forte.
    catalogo = {i: _filme(i, keywords=(100,)) for i in range(1, 11)}
    perfil = Profile(movies={1: Entry(seen=True, rating=1, want=False, at="2026-08-20")})
    gosto = construir_gosto(perfil, catalogo)

    assert abs(gosto.weights[("keyword", 100)]) < 0.1


def test_rejeicao_produz_peso_negativo():
    catalogo = {i: _filme(i) for i in range(1, 11)}
    catalogo[1] = _filme(1, keywords=(200,))

    perfil = Profile(movies={1: Entry(seen=True, rating=-1, want=False, at="2026-08-20")})
    gosto = construir_gosto(perfil, catalogo)

    assert gosto.weights[("keyword", 200)] < 0


def test_suavizacao_impede_conviccao_a_partir_de_uma_observacao():
    catalogo = {i: _filme(i) for i in range(1, 11)}
    catalogo[1] = _filme(1, keywords=(200,))
    perfil = Profile(movies={1: Entry(seen=True, rating=1, want=False, at="2026-08-20")})

    gosto = construir_gosto(perfil, catalogo, k=2.0)
    idf = math.log(10 / 2)
    # afinidade = (1-0)/(1+0+2) = 1/3, e não 1.0
    assert gosto.weights[("keyword", 200)] == pytest.approx(idf / 3)


def test_gosto_de_um_filme_usa_so_aquele_filme():
    catalogo = {i: _filme(i) for i in range(1, 11)}
    catalogo[5] = _filme(5, keywords=(200,), directors=(77,))

    gosto = gosto_de_um_filme(catalogo[5], catalogo)

    assert gosto.n_ratings == 1
    assert gosto.weights[("director", 77)] > 0


def test_contagem_de_avaliacoes_ignora_filmes_fora_do_catalogo():
    catalogo = {1: _filme(1)}
    perfil = Profile(
        movies={
            1: Entry(seen=True, rating=1, want=False, at="2026-08-20"),
            999: Entry(seen=True, rating=1, want=False, at="2026-08-20"),
        }
    )
    assert construir_gosto(perfil, catalogo).n_ratings == 1
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_profile.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.profile'`

- [ ] **Step 3: Implementar `sync/profile.py`**

```python
"""Perfil de avaliações e construção do vetor de gosto."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sync.catalog import Movie


@dataclass(frozen=True)
class Entry:
    seen: bool = False
    rating: int | None = None
    want: bool = False
    at: str = ""


@dataclass(frozen=True)
class Profile:
    movies: dict[int, Entry] = field(default_factory=dict)

    def liked_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.rating == 1}

    def disliked_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.rating == -1}

    def seen_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.seen}

    def wanted_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.want}


def ler_perfil(caminho: Path) -> Profile:
    if not caminho.exists():
        return Profile()

    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Profile(
        movies={
            int(id_): Entry(
                seen=dados.get("seen", False),
                rating=dados.get("rating"),
                want=dados.get("want", False),
                at=dados.get("at", ""),
            )
            for id_, dados in (bruto.get("movies") or {}).items()
        }
    )


def features_of(filme: Movie) -> dict[str, tuple]:
    """Decompõe um filme no saco de características que o motor compara."""
    return {
        "keyword": filme.keywords,
        "director": filme.directors,
        "cast": filme.cast,
        "genre": filme.genres,
        "decade": ((filme.year // 10) * 10,) if filme.year else (),
        "language": (filme.language,) if filme.language else (),
    }


@dataclass(frozen=True)
class Taste:
    weights: dict[tuple[str, object], float]
    n_ratings: int


def _frequencia_no_catalogo(catalogo: dict[int, Movie]) -> Counter:
    frequencia: Counter = Counter()
    for filme in catalogo.values():
        for tipo, valores in features_of(filme).items():
            for valor in set(valores):
                frequencia[(tipo, valor)] += 1
    return frequencia


def _pesar(
    curtidos: list[Movie],
    rejeitados: list[Movie],
    catalogo: dict[int, Movie],
    k: float,
) -> dict[tuple[str, object], float]:
    frequencia = _frequencia_no_catalogo(catalogo)
    total = max(len(catalogo), 1)

    positivos: Counter = Counter()
    negativos: Counter = Counter()
    for filme in curtidos:
        for tipo, valores in features_of(filme).items():
            for valor in set(valores):
                positivos[(tipo, valor)] += 1
    for filme in rejeitados:
        for tipo, valores in features_of(filme).items():
            for valor in set(valores):
                negativos[(tipo, valor)] += 1

    pesos: dict[tuple[str, object], float] = {}
    for caracteristica in set(positivos) | set(negativos):
        p = positivos[caracteristica]
        n = negativos[caracteristica]
        # Suavização bayesiana: uma única observação não vira convicção.
        afinidade = (p - n) / (p + n + k)
        # Normalização por raridade: o que é comum não discrimina.
        idf = math.log(total / (1 + frequencia.get(caracteristica, 0)))
        pesos[caracteristica] = afinidade * idf

    return pesos


def construir_gosto(
    perfil: Profile, catalogo: dict[int, Movie], *, k: float = 2.0
) -> Taste:
    curtidos = [catalogo[i] for i in perfil.liked_ids() if i in catalogo]
    rejeitados = [catalogo[i] for i in perfil.disliked_ids() if i in catalogo]
    return Taste(
        weights=_pesar(curtidos, rejeitados, catalogo, k),
        n_ratings=len(curtidos) + len(rejeitados),
    )


def gosto_de_um_filme(
    filme: Movie, catalogo: dict[int, Movie], *, k: float = 2.0
) -> Taste:
    """Vetor de gosto derivado de um único filme, para 'o que se parece
    com esse'."""
    return Taste(weights=_pesar([filme], [], catalogo, k), n_ratings=1)
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_profile.py -v`
Expected: PASS, 9 testes

- [ ] **Step 5: Commit**

```bash
git add sync/profile.py tests/test_profile.py
git commit -m "feat: vetor de gosto com normalizacao por raridade"
```

---

### Task 8: Motor de pontuação

A peça de maior risco do projeto: um ranking errado não quebra nada, apenas decepciona em silêncio. Concentra os testes mais importantes, incluindo o da redistribuição de peso — sem ela o motor esconderia justamente os filmes obscuros que o Fabio quer descobrir.

**Files:**
- Create: `sync/score.py`
- Create: `tests/test_score.py`

**Interfaces:**
- Consumes: `Movie` (Task 6), `Taste`, `features_of` (Task 7), `Motor` (Task 4).
- Produces:
  - `def afinidade(filme: Movie, gosto: Taste, pesos: dict[str, float]) -> float`
  - `def qualidade_bayesiana(media: float, votos: int, *, m: int, media_global: float) -> float`
  - `@dataclass(frozen=True) class Scoring` com `scores: dict[int, float]`, `affinities: dict[int, float]`, `qualities: dict[int, float]`
  - `def pontuar(catalogo: dict[int, Movie], gosto: Taste, cfg: Motor) -> Scoring`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_score.py`:

```python
from sync.catalog import Movie
from sync.config import Motor
from sync.profile import Taste
from sync.score import afinidade, pontuar, qualidade_bayesiana

PESOS = {
    "keyword": 0.40, "director": 0.20, "cast": 0.15,
    "genre": 0.15, "decade": 0.06, "language": 0.04,
}


def _motor(**extras) -> Motor:
    base = dict(
        suavizacao_k=2.0, qualidade_m=500, peso_afinidade=0.75,
        min_avaliacoes=10, pesos=PESOS,
    )
    return Motor(**{**base, **extras})


def _filme(id_=1, *, keywords=(), genres=(), year=None, media=7.0, votos=100) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=100,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=media, vote_count=votos,
        directors=(), cast=(), language="",
        track="acervo", theatrical=False, added="2026-08-27",
    )


def test_filme_sem_keywords_nao_e_penalizado():
    """O teste central da redistribuição de peso.

    Dois filmes com o mesmo sinal de gênero: um tem keyword igualmente
    positiva, o outro não tem keyword nenhuma. O segundo não pode afundar
    só porque o TMDB não catalogou suas palavras-chave.
    """
    gosto = Taste(weights={("genre", 18): 1.0, ("keyword", 200): 1.0}, n_ratings=20)

    completo = _filme(1, genres=(18,), keywords=(200,))
    sem_keyword = _filme(2, genres=(18,))

    assert afinidade(completo, gosto, PESOS) == 1.0
    assert afinidade(sem_keyword, gosto, PESOS) == 1.0


def test_sem_redistribuicao_o_valor_seria_muito_menor():
    # Guarda contra uma regressão para a implementação ingênua, que daria
    # 0.15 (só a fatia do gênero) em vez de 1.0.
    gosto = Taste(weights={("genre", 18): 1.0}, n_ratings=20)
    assert afinidade(_filme(1, genres=(18,)), gosto, PESOS) > 0.9


def test_afinidade_e_zero_quando_nao_ha_caracteristica_conhecida():
    gosto = Taste(weights={("genre", 99): 1.0}, n_ratings=20)
    assert afinidade(_filme(1, genres=(18,)), gosto, PESOS) == 0.0


def test_afinidade_negativa_quando_o_sinal_e_de_rejeicao():
    gosto = Taste(weights={("genre", 18): -1.0}, n_ratings=20)
    assert afinidade(_filme(1, genres=(18,)), gosto, PESOS) < 0


def test_qualidade_puxa_poucos_votos_para_a_media_global():
    alto_e_raro = qualidade_bayesiana(9.8, 51, m=500, media_global=6.0)
    alto_e_consolidado = qualidade_bayesiana(8.2, 25000, m=500, media_global=6.0)

    assert alto_e_raro < alto_e_consolidado


def test_partida_a_frio_ignora_a_afinidade():
    catalogo = {
        1: _filme(1, genres=(18,), media=9.0, votos=10000),
        2: _filme(2, genres=(18,), media=5.0, votos=10000),
    }
    gosto = Taste(weights={("genre", 18): 5.0}, n_ratings=3)

    resultado = pontuar(catalogo, gosto, _motor())

    # Com menos de 10 avaliações o score é qualidade pura, então o filme de
    # nota alta vence mesmo que ambos tenham a mesma afinidade.
    assert resultado.scores[1] > resultado.scores[2]
    assert resultado.affinities[1] == resultado.affinities[2]


def test_com_perfil_maduro_a_afinidade_domina():
    catalogo = {
        1: _filme(1, genres=(18,), media=6.0, votos=10000),
        2: _filme(2, genres=(99,), media=8.0, votos=10000),
    }
    gosto = Taste(weights={("genre", 18): 5.0, ("genre", 99): -5.0}, n_ratings=40)

    resultado = pontuar(catalogo, gosto, _motor())

    assert resultado.scores[1] > resultado.scores[2]


def test_scores_ficam_entre_zero_e_um():
    catalogo = {i: _filme(i, genres=(18,), media=float(i), votos=1000) for i in range(1, 9)}
    gosto = Taste(weights={("genre", 18): 1.0}, n_ratings=40)

    resultado = pontuar(catalogo, gosto, _motor())

    assert all(0.0 <= s <= 1.0 for s in resultado.scores.values())


def test_catalogo_vazio_nao_quebra():
    resultado = pontuar({}, Taste(weights={}, n_ratings=40), _motor())
    assert resultado.scores == {}
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_score.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.score'`

- [ ] **Step 3: Implementar `sync/score.py`**

```python
"""Motor de pontuação: afinidade com o gosto mais âncora de qualidade."""

from __future__ import annotations

from dataclasses import dataclass

from sync.catalog import Movie
from sync.config import Motor
from sync.profile import Taste, features_of

NOTA_MAXIMA = 10.0


def afinidade(filme: Movie, gosto: Taste, pesos: dict[str, float]) -> float:
    """Média dos pesos das características do filme, ponderada por tipo.

    Tipos ausentes têm seu peso redistribuído proporcionalmente entre os
    presentes. Sem isso, um filme sem keywords perderia 40% do score por
    uma lacuna do TMDB, e não por discordância de gosto — penalizando
    sistematicamente os filmes obscuros.
    """
    presentes: dict[str, float] = {}

    for tipo, valores in features_of(filme).items():
        unicos = set(valores)
        if not unicos:
            continue
        soma = sum(gosto.weights.get((tipo, v), 0.0) for v in unicos)
        presentes[tipo] = soma / len(unicos)

    if not presentes:
        return 0.0

    total = sum(pesos.get(tipo, 0.0) for tipo in presentes)
    if total == 0.0:
        return 0.0

    return sum(
        pesos.get(tipo, 0.0) / total * valor for tipo, valor in presentes.items()
    )


def qualidade_bayesiana(
    media: float, votos: int, *, m: int, media_global: float
) -> float:
    """Puxa notas apoiadas em poucos votos na direção da média global.

    Impede que um filme com nota 9,8 e 51 votos vença um consolidado.
    """
    return (votos / (votos + m)) * media + (m / (votos + m)) * media_global


@dataclass(frozen=True)
class Scoring:
    scores: dict[int, float]
    affinities: dict[int, float]
    qualities: dict[int, float]


def pontuar(catalogo: dict[int, Movie], gosto: Taste, cfg: Motor) -> Scoring:
    if not catalogo:
        return Scoring(scores={}, affinities={}, qualities={})

    media_global = sum(f.vote_average for f in catalogo.values()) / len(catalogo)

    qualidades = {
        id_: qualidade_bayesiana(
            filme.vote_average,
            filme.vote_count,
            m=cfg.qualidade_m,
            media_global=media_global,
        )
        / NOTA_MAXIMA
        for id_, filme in catalogo.items()
    }
    afinidades = {
        id_: afinidade(filme, gosto, cfg.pesos) for id_, filme in catalogo.items()
    }

    # Partida a frio: sem avaliações suficientes não há sinal utilizável,
    # então o ranking cai para qualidade pura.
    if gosto.n_ratings < cfg.min_avaliacoes:
        return Scoring(
            scores=dict(qualidades), affinities=afinidades, qualities=qualidades
        )

    menor = min(afinidades.values())
    maior = max(afinidades.values())
    amplitude = (maior - menor) or 1.0

    scores = {
        id_: cfg.peso_afinidade * ((afinidades[id_] - menor) / amplitude)
        + (1 - cfg.peso_afinidade) * qualidades[id_]
        for id_ in catalogo
    }
    return Scoring(scores=scores, affinities=afinidades, qualities=qualidades)
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_score.py -v`
Expected: PASS, 9 testes

- [ ] **Step 5: Commit**

```bash
git add sync/score.py tests/test_score.py
git commit -m "feat: motor de pontuacao com redistribuicao de peso"
```

---

### Task 9: Geração das fileiras

As onze fileiras da home. Cada uma é uma função pura que recebe o mesmo contexto e devolve ids ordenados. As fileiras *aposta* e *ponto cego* existem para combater a bolha que o próprio motor cria — sem elas o sistema converge para mais do mesmo.

**Files:**
- Create: `sync/shelves.py`
- Create: `tests/test_shelves.py`
- Create: `data/vibes.json`

**Interfaces:**
- Consumes: `Movie` (6), `Profile`, `Taste`, `gosto_de_um_filme` (7), `Scoring`, `afinidade` (8), `Config` (4).
- Produces:
  - `@dataclass(frozen=True) class Shelf` com `key: str`, `title: str`, `movie_ids: tuple[int, ...]`
  - `@dataclass(frozen=True) class Contexto` com `catalogo`, `perfil`, `pontuacao`, `gosto`, `hoje: date`, `cfg: Config`, `vibes: dict[str, list[int]]`, `nomes: dict[str, dict[int, str]]`
  - `def montar_fileiras(ctx: Contexto) -> list[Shelf]`

- [ ] **Step 1: Criar `data/vibes.json` inicial**

Comece com 12 vibes; a expansão para ~250 é a pendência 5 do spec e não bloqueia nada.

```json
{
  "fim do mundo": [4458, 9951, 1701, 12565],
  "assalto": [10051, 779],
  "found footage": [15012],
  "vinganca": [9748],
  "viagem no tempo": [4379],
  "sobrevivencia": [10349],
  "distopia": [4565],
  "amadurecimento": [10683],
  "julgamento": [1930],
  "espionagem": [1583],
  "monstro gigante": [9951],
  "isolamento": [4426]
}
```

- [ ] **Step 2: Escrever os testes que falham**

Crie `tests/test_shelves.py`:

```python
from datetime import date

from sync.catalog import Movie
from sync.config import Build, Config, Motor, Admissao
from sync.profile import Entry, Profile, Taste
from sync.score import Scoring
from sync.shelves import Contexto, montar_fileiras

HOJE = date(2026, 8, 27)
PESOS = {
    "keyword": 0.40, "director": 0.20, "cast": 0.15,
    "genre": 0.15, "decade": 0.06, "language": 0.04,
}


def _cfg(fileiras: tuple[str, ...]) -> Config:
    return Config(
        admissao=Admissao(50, 18, 5, 8.0, 60),
        motor=Motor(2.0, 500, 0.75, 10, PESOS),
        build=Build(6.0, 3),
        fileiras=fileiras,
    )


def _filme(id_, *, year=2000, runtime=100, theatrical=False, added="2020-01-01",
           keywords=(), directors=(), genres=()) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=year, runtime=runtime,
        genres=tuple(genres), keywords=tuple(keywords),
        vote_average=7.0, vote_count=1000,
        directors=tuple(directors), cast=(), language="en",
        track="acervo", theatrical=theatrical, added=added,
    )


def _ctx(catalogo, perfil, fileiras, *, scores=None, gosto=None) -> Contexto:
    scores = scores or {i: 0.5 for i in catalogo}
    return Contexto(
        catalogo=catalogo,
        perfil=perfil,
        pontuacao=Scoring(scores=scores, affinities=dict(scores), qualities=dict(scores)),
        gosto=gosto or Taste(weights={}, n_ratings=40),
        hoje=HOJE,
        cfg=_cfg(fileiras),
        vibes={"fim do mundo": [900]},
        nomes={"director": {77: "Tarkovsky"}, "cast": {}},
    )


def test_watchlist_traz_apenas_os_marcados_como_quero_ver():
    catalogo = {1: _filme(1), 2: _filme(2)}
    perfil = Profile(movies={2: Entry(want=True, at="2026-08-01")})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("watchlist",)))

    assert fileiras[0].key == "watchlist"
    assert fileiras[0].movie_ids == (2,)


def test_novos_traz_apenas_os_admitidos_hoje():
    catalogo = {
        1: _filme(1, added="2026-08-27"),
        2: _filme(2, added="2026-08-26"),
    }
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("novos",)))
    assert fileiras[0].movie_ids == (1,)


def test_cinemas_traz_apenas_os_em_cartaz():
    catalogo = {1: _filme(1, theatrical=True), 2: _filme(2)}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("cinemas",)))
    assert fileiras[0].movie_ids == (1,)


def test_curto_filtra_por_duracao_e_exclui_vistos():
    catalogo = {1: _filme(1, runtime=95), 2: _filme(2, runtime=140), 3: _filme(3, runtime=90)}
    perfil = Profile(movies={3: Entry(seen=True, at="2026-08-01")})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("curto",)))

    assert fileiras[0].movie_ids == (1,)


def test_classicos_exige_25_anos_e_ausencia_no_perfil():
    catalogo = {
        1: _filme(1, year=1990),
        2: _filme(2, year=2020),
        3: _filme(3, year=1985),
    }
    perfil = Profile(movies={3: Entry(seen=True, at="2026-08-01")})

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("classicos",)))

    assert fileiras[0].movie_ids == (1,)


def test_diretor_usa_o_de_maior_peso_no_gosto():
    catalogo = {
        1: _filme(1, directors=(77,)),
        2: _filme(2, directors=(88,)),
        3: _filme(3, directors=(77,)),
    }
    perfil = Profile(movies={3: Entry(seen=True, at="2026-08-01")})
    gosto = Taste(weights={("director", 77): 2.0, ("director", 88): 0.1}, n_ratings=40)

    fileiras = montar_fileiras(_ctx(catalogo, perfil, ("diretor",), gosto=gosto))

    assert fileiras[0].movie_ids == (1,)
    assert "Tarkovsky" in fileiras[0].title


def test_vibe_e_estavel_no_mesmo_dia_e_filtra_por_keyword():
    catalogo = {1: _filme(1, keywords=(900,)), 2: _filme(2, keywords=(1,))}
    ctx = _ctx(catalogo, Profile(), ("vibe",))

    primeira = montar_fileiras(ctx)[0]
    segunda = montar_fileiras(ctx)[0]

    assert primeira.title == segunda.title
    assert primeira.movie_ids == (1,)


def test_fileira_vazia_e_omitida():
    catalogo = {1: _filme(1)}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("watchlist", "novos")))
    assert fileiras == []


def test_respeita_a_ordem_configurada():
    catalogo = {1: _filme(1, theatrical=True, added="2026-08-27")}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("cinemas", "novos")))
    assert [f.key for f in fileiras] == ["cinemas", "novos"]


def test_tamanho_da_fileira_respeita_o_config():
    catalogo = {i: _filme(i, added="2026-08-27") for i in range(1, 11)}
    fileiras = montar_fileiras(_ctx(catalogo, Profile(), ("novos",)))
    assert len(fileiras[0].movie_ids) == 3  # Build.tamanho_fileira do _cfg
```

- [ ] **Step 3: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_shelves.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.shelves'`

- [ ] **Step 4: Implementar `sync/shelves.py`**

```python
"""Montagem das fileiras da home."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from sync.catalog import Movie
from sync.config import Config
from sync.profile import Profile, Taste, features_of, gosto_de_um_filme
from sync.score import Scoring, afinidade

ANOS_PARA_CLASSICO = 25
DURACAO_CURTA = 100
MIN_FILMES_PARA_DIMENSAO = 200


@dataclass(frozen=True)
class Shelf:
    key: str
    title: str
    movie_ids: tuple[int, ...]


@dataclass(frozen=True)
class Contexto:
    catalogo: dict[int, Movie]
    perfil: Profile
    pontuacao: Scoring
    gosto: Taste
    hoje: date
    cfg: Config
    vibes: dict[str, list[int]]
    nomes: dict[str, dict[int, str]]


def _ordenar(ctx: Contexto, ids) -> tuple[int, ...]:
    limite = ctx.cfg.build.tamanho_fileira
    return tuple(
        sorted(ids, key=lambda i: ctx.pontuacao.scores.get(i, 0.0), reverse=True)
    )[:limite]


def _nao_vistos(ctx: Contexto) -> set[int]:
    return set(ctx.catalogo) - ctx.perfil.seen_ids()


def _percentil(valores: list[float], fracao: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(int(len(ordenados) * fracao), len(ordenados) - 1)
    return ordenados[indice]


def _melhor_do_tipo(ctx: Contexto, tipo: str) -> object | None:
    candidatos = {
        valor: peso
        for (t, valor), peso in ctx.gosto.weights.items()
        if t == tipo and peso > 0
    }
    return max(candidatos, key=candidatos.get) if candidatos else None


# --- as onze fileiras ------------------------------------------------------


def _watchlist(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = ctx.perfil.wanted_ids() & set(ctx.catalogo)
    return "Você marcou pra ver", _ordenar(ctx, ids)


def _novos(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    hoje = ctx.hoje.isoformat()
    ids = {i for i, f in ctx.catalogo.items() if f.added == hoje}
    return "Entrou hoje no catálogo", _ordenar(ctx, ids - ctx.perfil.seen_ids())


def _similar(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    curtidos = [
        (ctx.perfil.movies[i].at, i)
        for i in ctx.perfil.liked_ids()
        if i in ctx.catalogo
    ]
    if not curtidos:
        return "", ()

    _, referencia = max(curtidos)
    filme = ctx.catalogo[referencia]
    gosto = gosto_de_um_filme(filme, ctx.catalogo)

    candidatos = _nao_vistos(ctx) - {referencia}
    afinidades = {
        i: afinidade(ctx.catalogo[i], gosto, ctx.cfg.motor.pesos) for i in candidatos
    }
    melhores = sorted(afinidades, key=afinidades.get, reverse=True)
    limite = ctx.cfg.build.tamanho_fileira
    return f"Porque você gostou de {filme.title}", tuple(melhores[:limite])


def _vibe(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    if not ctx.vibes:
        return "", ()

    # Semente na data: a vibe é sorteada, mas estável ao longo do dia.
    nomes = sorted(ctx.vibes)
    escolhida = nomes[ctx.hoje.toordinal() % len(nomes)]
    alvo = set(ctx.vibes[escolhida])

    ids = {
        i
        for i in _nao_vistos(ctx)
        if alvo & set(ctx.catalogo[i].keywords)
    }
    return f"Hoje a vibe é: {escolhida}", _ordenar(ctx, ids)


def _por_pessoa(ctx: Contexto, tipo: str, rotulo: str) -> tuple[str, tuple[int, ...]]:
    pessoa = _melhor_do_tipo(ctx, tipo)
    if pessoa is None:
        return "", ()

    ids = {
        i
        for i in _nao_vistos(ctx)
        if pessoa in features_of(ctx.catalogo[i])[tipo]
    }
    nome = ctx.nomes.get(tipo, {}).get(pessoa, str(pessoa))
    return f"{rotulo} {nome}", _ordenar(ctx, ids)


def _diretor(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    return _por_pessoa(ctx, "director", "Mais de")


def _ator(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    return _por_pessoa(ctx, "cast", "Com")


def _curto(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = {i for i in _nao_vistos(ctx) if ctx.catalogo[i].runtime < DURACAO_CURTA}
    return "Cabe antes de dormir", _ordenar(ctx, ids)


def _classicos(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    limite_ano = ctx.hoje.year - ANOS_PARA_CLASSICO
    corte = _percentil(list(ctx.pontuacao.qualities.values()), 0.98)

    ids = {
        i
        for i, filme in ctx.catalogo.items()
        if filme.year is not None
        and filme.year <= limite_ano
        and ctx.pontuacao.qualities.get(i, 0.0) >= corte
        and i not in ctx.perfil.movies
    }
    return "Clássicos que você nunca viu", _ordenar(ctx, ids)


def _aposta(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    candidatos = _nao_vistos(ctx)
    if not candidatos:
        return "", ()

    afins = [ctx.pontuacao.affinities.get(i, 0.0) for i in candidatos]
    piso = _percentil(afins, 0.40)
    teto = _percentil(afins, 0.70)
    corte_qualidade = _percentil(list(ctx.pontuacao.qualities.values()), 0.95)

    ids = {
        i
        for i in candidatos
        if piso <= ctx.pontuacao.affinities.get(i, 0.0) <= teto
        and ctx.pontuacao.qualities.get(i, 0.0) >= corte_qualidade
    }
    return "Aposta arriscada", _ordenar(ctx, ids)


def _ponto_cego(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    """A dimensão de menor razão entre presença nos curtidos e presença no
    catálogo — o antídoto contra a bolha que o motor cria sozinho."""
    curtidos = [ctx.catalogo[i] for i in ctx.perfil.liked_ids() if i in ctx.catalogo]
    if not curtidos:
        return "", ()

    no_catalogo: Counter = Counter()
    for filme in ctx.catalogo.values():
        for tipo in ("genre", "language", "decade"):
            for valor in set(features_of(filme)[tipo]):
                no_catalogo[(tipo, valor)] += 1

    nos_curtidos: Counter = Counter()
    for filme in curtidos:
        for tipo in ("genre", "language", "decade"):
            for valor in set(features_of(filme)[tipo]):
                nos_curtidos[(tipo, valor)] += 1

    elegiveis = {
        chave: nos_curtidos[chave] / total
        for chave, total in no_catalogo.items()
        if total >= MIN_FILMES_PARA_DIMENSAO
    }
    if not elegiveis:
        return "", ()

    alvo = min(elegiveis, key=elegiveis.get)
    tipo, valor = alvo
    corte = _percentil(list(ctx.pontuacao.qualities.values()), 0.98)

    ids = {
        i
        for i in _nao_vistos(ctx)
        if valor in features_of(ctx.catalogo[i])[tipo]
        and ctx.pontuacao.qualities.get(i, 0.0) >= corte
    }
    return "Ponto cego", _ordenar(ctx, ids)


def _cinemas(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = {i for i, filme in ctx.catalogo.items() if filme.theatrical}
    return "Nos cinemas", _ordenar(ctx, ids)


GERADORES = {
    "watchlist": _watchlist,
    "novos": _novos,
    "similar": _similar,
    "vibe": _vibe,
    "diretor": _diretor,
    "ator": _ator,
    "curto": _curto,
    "classicos": _classicos,
    "aposta": _aposta,
    "ponto_cego": _ponto_cego,
    "cinemas": _cinemas,
}


def montar_fileiras(ctx: Contexto) -> list[Shelf]:
    """Monta as fileiras na ordem do config, omitindo as que ficaram vazias."""
    fileiras: list[Shelf] = []

    for chave in ctx.cfg.fileiras:
        gerador = GERADORES.get(chave)
        if gerador is None:
            continue
        titulo, ids = gerador(ctx)
        if ids:
            fileiras.append(Shelf(key=chave, title=titulo, movie_ids=ids))

    return fileiras
```

- [ ] **Step 5: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_shelves.py -v`
Expected: PASS, 10 testes

- [ ] **Step 6: Commit**

```bash
git add sync/shelves.py tests/test_shelves.py data/vibes.json
git commit -m "feat: geracao das onze fileiras da home"
```

---

### Task 10: Build dos artefatos do site

Escreve o contrato que o Plano 2 vai consumir. Inclui o teste de tamanho: se o índice crescer além do limite, o build falha — sem isso o site degrada silenciosamente até ficar lento no celular e ninguém percebe.

**Files:**
- Create: `sync/build.py`
- Create: `tests/test_build.py`

**Interfaces:**
- Consumes: `Movie` (6), `Scoring` (8), `Shelf` (9), `Build` (4).
- Produces:
  - `class IndiceGrandeDemais(RuntimeError)`
  - `def escrever_site_data(destino: Path, catalogo: dict[int, Movie], pontuacao: Scoring, fileiras: list[Shelf], cfg: Build) -> None`

Contrato dos arquivos gerados, consumido pelo Plano 2:

- `index.json` — `{"movies": [{"id","t","y","r","g","k","s"}, ...]}` ordenado por `s` decrescente, onde `s` é o score arredondado em 4 casas.
- `shelves.json` — `{"shelves": [{"key","title","ids"}, ...]}`
- `keywords.json` — `{"<keyword_id>": [movie_id, ...]}`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_build.py`:

```python
import json
from pathlib import Path

import pytest

from sync.build import IndiceGrandeDemais, escrever_site_data
from sync.catalog import Movie
from sync.config import Build
from sync.score import Scoring
from sync.shelves import Shelf


def _filme(id_, *, keywords=()) -> Movie:
    return Movie(
        id=id_, title=f"F{id_}", year=2000, runtime=100,
        genres=(18,), keywords=tuple(keywords),
        vote_average=7.0, vote_count=1000,
        directors=(), cast=(), language="en",
        track="acervo", theatrical=False, added="2026-08-27",
    )


def _pontuacao(scores: dict[int, float]) -> Scoring:
    return Scoring(scores=scores, affinities=dict(scores), qualities=dict(scores))


def test_escreve_os_tres_arquivos(tmp_path: Path):
    catalogo = {1: _filme(1, keywords=(900,))}
    escrever_site_data(
        tmp_path, catalogo, _pontuacao({1: 0.5}),
        [Shelf("novos", "Entrou hoje", (1,))], Build(6.0, 24),
    )

    assert (tmp_path / "index.json").exists()
    assert (tmp_path / "shelves.json").exists()
    assert (tmp_path / "keywords.json").exists()


def test_index_vem_ordenado_por_score_decrescente(tmp_path: Path):
    catalogo = {1: _filme(1), 2: _filme(2), 3: _filme(3)}
    escrever_site_data(
        tmp_path, catalogo, _pontuacao({1: 0.1, 2: 0.9, 3: 0.5}), [], Build(6.0, 24)
    )

    dados = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [m["id"] for m in dados["movies"]] == [2, 3, 1]


def test_indice_invertido_agrupa_por_keyword(tmp_path: Path):
    catalogo = {1: _filme(1, keywords=(900,)), 2: _filme(2, keywords=(900, 901))}
    escrever_site_data(tmp_path, catalogo, _pontuacao({1: 0.5, 2: 0.5}), [], Build(6.0, 24))

    dados = json.loads((tmp_path / "keywords.json").read_text(encoding="utf-8"))
    assert sorted(dados["900"]) == [1, 2]
    assert dados["901"] == [2]


def test_falha_quando_o_indice_passa_do_limite(tmp_path: Path):
    catalogo = {i: _filme(i) for i in range(500)}
    with pytest.raises(IndiceGrandeDemais):
        escrever_site_data(
            tmp_path, catalogo, _pontuacao({i: 0.5 for i in range(500)}),
            [], Build(0.00001, 24),
        )


def test_score_e_arredondado(tmp_path: Path):
    catalogo = {1: _filme(1)}
    escrever_site_data(tmp_path, catalogo, _pontuacao({1: 0.123456789}), [], Build(6.0, 24))

    dados = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert dados["movies"][0]["s"] == 0.1235
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_build.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.build'`

- [ ] **Step 3: Implementar `sync/build.py`**

```python
"""Escrita dos artefatos consumidos pelo site."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sync.catalog import Movie
from sync.config import Build
from sync.score import Scoring
from sync.shelves import Shelf

BYTES_POR_MB = 1024 * 1024


class IndiceGrandeDemais(RuntimeError):
    """O índice passou do limite configurado e degradaria o carregamento."""


def _escrever(caminho: Path, dados: object) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(texto, encoding="utf-8")
    return len(texto.encode("utf-8"))


def escrever_site_data(
    destino: Path,
    catalogo: dict[int, Movie],
    pontuacao: Scoring,
    fileiras: list[Shelf],
    cfg: Build,
) -> None:
    ordenados = sorted(
        catalogo.values(),
        key=lambda f: pontuacao.scores.get(f.id, 0.0),
        reverse=True,
    )

    indice = {
        "movies": [
            {
                "id": f.id,
                "t": f.title,
                "y": f.year,
                "r": f.runtime,
                "g": list(f.genres),
                "k": list(f.keywords),
                "s": round(pontuacao.scores.get(f.id, 0.0), 4),
            }
            for f in ordenados
        ]
    }
    tamanho = _escrever(destino / "index.json", indice)

    limite = cfg.limite_index_mb * BYTES_POR_MB
    if tamanho > limite:
        raise IndiceGrandeDemais(
            f"index.json tem {tamanho / BYTES_POR_MB:.2f} MB, "
            f"acima do limite de {cfg.limite_index_mb} MB"
        )

    _escrever(
        destino / "shelves.json",
        {
            "shelves": [
                {"key": s.key, "title": s.title, "ids": list(s.movie_ids)}
                for s in fileiras
            ]
        },
    )

    invertido: dict[int, list[int]] = defaultdict(list)
    for filme in catalogo.values():
        for keyword in filme.keywords:
            invertido[keyword].append(filme.id)

    _escrever(
        destino / "keywords.json",
        {str(k): sorted(v) for k, v in sorted(invertido.items())},
    )
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_build.py -v`
Expected: PASS, 5 testes

- [ ] **Step 5: Commit**

```bash
git add sync/build.py tests/test_build.py
git commit -m "feat: escrita dos artefatos do site com teste de tamanho"
```

---

### Task 11: Orquestração, atomicidade e carga inicial

Amarra tudo num CLI com dois modos. A atomicidade é o requisito central: publicar meio catálogo é pior que publicar um catálogo velho, então nada é movido para o lugar definitivo enquanto todas as etapas não passarem.

**Files:**
- Create: `sync/enrich.py`
- Create: `sync/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: tudo das tasks anteriores.
- Produces:
  - `async def buscar_detalhes(cliente: TMDBClient, ids: Iterable[int], *, concorrencia: int = 16) -> list[dict]`
  - `def publicar_atomico(temporario: Path, definitivo: Path) -> None`
  - `async def executar(*, raiz: Path, token: str, hoje: date, carga_inicial: bool) -> None`
  - `def main() -> None` — entrada de `python -m sync`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_cli.py`:

```python
import httpx
import pytest
import respx

from sync.cli import publicar_atomico
from sync.enrich import buscar_detalhes
from sync.tmdb import TMDBClient, TMDBError


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
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_cli.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'sync.cli'`

- [ ] **Step 3: Implementar `sync/enrich.py`**

```python
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
```

- [ ] **Step 4: Implementar `sync/cli.py`**

```python
"""Orquestração do pipeline. Publica tudo ou não publica nada."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from sync.admission import classificar
from sync.build import escrever_site_data
from sync.catalog import escrever_catalogo, ler_catalogo, montar_filme
from sync.config import carregar_config
from sync.discover import descobrir_fatiado
from sync.enrich import buscar_detalhes
from sync.exports import baixar_export, ids_novos
from sync.profile import construir_gosto, ler_perfil
from sync.score import pontuar
from sync.shelves import Contexto, montar_fileiras
from sync.theatrical import apenas_no_cinema
from sync.tmdb import TMDBClient

import json


def publicar_atomico(temporario: Path, definitivo: Path) -> None:
    """Troca o conteúdo do destino de uma vez.

    Um catálogo pela metade é pior que um catálogo de ontem, então a
    publicação só acontece depois que tudo foi gerado com sucesso.
    """
    definitivo.parent.mkdir(parents=True, exist_ok=True)
    if definitivo.exists():
        shutil.rmtree(definitivo)
    shutil.move(str(temporario), str(definitivo))


async def _ids_para_processar(
    cliente: TMDBClient, raiz: Path, hoje: date, carga_inicial: bool
) -> set[int]:
    if carga_inicial:
        # Sem estado anterior: varre o discover inteiro, fatiado por ano.
        resultados = await descobrir_fatiado(
            cliente,
            {"language": "pt-BR", "region": "BR", "sort_by": "popularity.desc"},
            ano_final=hoje.year,
        )
        return {r["id"] for r in resultados}

    export_hoje = await baixar_export(hoje)
    caminho_ontem = raiz / "data" / "tmdb_ids_ontem.json"
    if caminho_ontem.exists():
        ontem = set(json.loads(caminho_ontem.read_text(encoding="utf-8")))
    else:
        ontem = await baixar_export(hoje - timedelta(days=1))

    caminho_ontem.parent.mkdir(parents=True, exist_ok=True)
    caminho_ontem.write_text(json.dumps(sorted(export_hoje)), encoding="utf-8")
    return ids_novos(export_hoje, ontem)


async def executar(
    *, raiz: Path, token: str, hoje: date, carga_inicial: bool
) -> None:
    cfg = carregar_config(raiz / "config.json")
    catalogo = ler_catalogo(raiz / "data" / "catalog.jsonl")
    perfil = ler_perfil(raiz / "data" / "profile.json")

    async with TMDBClient(token) as cliente:
        alvos = await _ids_para_processar(cliente, raiz, hoje, carga_inicial)
        novos = [i for i in alvos if i not in catalogo]
        detalhes = await buscar_detalhes(cliente, novos)

    nomes: dict[str, dict[int, str]] = {"director": {}, "cast": {}}

    for detalhe in detalhes:
        trilha = classificar(detalhe, hoje, cfg.admissao)
        if trilha is None:
            continue
        filme = montar_filme(
            detalhe,
            track=trilha,
            theatrical=apenas_no_cinema(detalhe.get("release_dates") or {}, hoje),
            added=hoje.isoformat(),
        )
        catalogo[filme.id] = filme

        creditos = detalhe.get("credits") or {}
        for pessoa in creditos.get("crew") or []:
            if pessoa.get("job") == "Director":
                nomes["director"][pessoa["id"]] = pessoa.get("name", "")
        for pessoa in (creditos.get("cast") or [])[:5]:
            nomes["cast"][pessoa["id"]] = pessoa.get("name", "")

    # Filmes sempre entram se o Fabio já os avaliou, mesmo fora dos cortes.
    protegidos = set(perfil.movies)
    limite_recente = hoje - timedelta(days=cfg.admissao.meses_recente * 30)
    catalogo = {
        i: f
        for i, f in catalogo.items()
        if f.track == "acervo"
        or i in protegidos
        or date.fromisoformat(f.added) >= limite_recente
    }

    gosto = construir_gosto(perfil, catalogo, k=cfg.motor.suavizacao_k)
    pontuacao = pontuar(catalogo, gosto, cfg.motor)

    vibes = json.loads((raiz / "data" / "vibes.json").read_text(encoding="utf-8"))
    fileiras = montar_fileiras(
        Contexto(
            catalogo=catalogo, perfil=perfil, pontuacao=pontuacao, gosto=gosto,
            hoje=hoje, cfg=cfg, vibes=vibes, nomes=nomes,
        )
    )

    temporario = Path(tempfile.mkdtemp(prefix="fdf-"))
    escrever_site_data(temporario, catalogo, pontuacao, fileiras, cfg.build)
    escrever_catalogo(raiz / "data" / "catalog.jsonl", catalogo.values())
    publicar_atomico(temporario, raiz / "site" / "data")


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync")
    parser.add_argument(
        "--carga-inicial",
        action="store_true",
        help="varre o discover inteiro em vez de usar o export diário",
    )
    parser.add_argument("--raiz", type=Path, default=Path("."))
    args = parser.parse_args()

    token = os.environ.get("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN não está definido no ambiente")

    asyncio.run(
        executar(
            raiz=args.raiz,
            token=token,
            hoje=date.today(),
            carga_inicial=args.carga_inicial,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Criar `sync/__main__.py`**

```python
from sync.cli import main

main()
```

- [ ] **Step 6: Rodar a suíte inteira**

Run: `.venv/Scripts/pytest -v`
Expected: PASS em todos os arquivos de teste

- [ ] **Step 7: Commit**

```bash
git add sync/enrich.py sync/cli.py sync/__main__.py tests/test_cli.py
git commit -m "feat: orquestracao do pipeline com publicacao atomica"
```

- [ ] **Step 8: Executar a carga inicial de verdade**

Este é o único passo que fala com o TMDB real. Leva de 15 a 40 minutos.

```bash
export TMDB_TOKEN='<o token v4 do Fabio>'
.venv/Scripts/python -m sync --carga-inicial
```

- [ ] **Step 9: Calibrar o piso de popularidade e conferir o volume**

Pendência 3 do spec. Confira o que a carga produziu:

```bash
wc -l data/catalog.jsonl
ls -la site/data/
```

Esperado: entre 35.000 e 50.000 linhas, `index.json` abaixo de 6 MB. Se o
volume vier muito acima, aumente `min_popularidade_recente` em `config.json`;
muito abaixo, diminua. Rode de novo e confirme.

- [ ] **Step 10: Commit do catálogo inicial**

```bash
git add data/catalog.jsonl data/tmdb_ids_ontem.json config.json
git commit -m "chore: carga inicial do catalogo"
```

---

## Cobertura do spec

Rastreamento das seções do spec contra as tasks deste plano.

| Seção do spec | Onde é implementada |
|---|---|
| 4.1 `catalog.jsonl` | Task 6 |
| 4.2 `profile.json` (leitura) | Task 7 · escrita fica no Plano 2 |
| 4.3 `vibes.json` | Task 9 (12 vibes iniciais; expansão é pendência) |
| 5 pipeline diário | Task 11 |
| 5.1 regras de admissão | Task 4 |
| 5.2 "nos cinemas" | Task 5 |
| 5.3 teto do `/discover` | Task 2 |
| 6.1 vetor de gosto | Task 7 |
| 6.2 pontuação e redistribuição | Task 8 |
| 6.3 partida a frio (motor) | Task 8 · a tela de onboarding fica no Plano 2 |
| 6.4 "gostei de X" | Task 7 (`gosto_de_um_filme`) e Task 9 (fileira `similar`) |
| 7.1 as onze fileiras | Task 9 |
| 7.2 grade · 7.3 ficha · 7.4 busca por vibe | **Plano 2** |
| 8 persistência do perfil | **Plano 2** |
| 9 build atômico e falhas | Tasks 1 e 11 |
| 11 testes | distribuídos; o teste de tamanho está na Task 10 |
| 12 atribuição ao TMDB | **Plano 2** (rodapé do site) |

Fora do escopo deste plano, por decisão: site, escrita do perfil pelo
navegador, workflow do GitHub Actions e abertura de issue em falha.

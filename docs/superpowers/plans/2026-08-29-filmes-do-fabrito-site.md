# Filmes do Fabrito — Plano 2: o site

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o site estático — HTML/CSS/JS sem framework e sem etapa
de build — que lê os artefatos que o Plano 1 já publica, mostra as onze
fileiras da home, a grade filtrável, a ficha do filme, a busca por vibe, o
onboarding de partida a frio, e escreve as avaliações do Fabio de volta no
repositório via API do GitHub.

**Architecture:** Módulos de lógica pura (`store`, `motor`, `vibes`,
`github`, `router`, `onboarding`) testados com o test runner nativo do Node,
sem dependência instalada. Um único módulo de renderização (`ui`) manipula
DOM diretamente e é verificado visualmente via a ferramenta de navegador, não
por asserção unitária — decisão registrada no documento de design. Hash
routing entre três telas em escada: home → grade → ficha. Hospedagem via
GitHub Pages servindo a raiz do repositório (não só `site/`), o que torna
`data/*.json` na raiz e `config.json` alcançáveis por caminho relativo sem
nenhum passo de deploy adicional.

**Tech Stack:** HTML, CSS, JavaScript com módulos ES nativos do navegador.
Node.js 18+ só para rodar os testes de lógica pura (`node:test`), zero
dependência de npm. Python 3.12 para as extensões pontuais do pipeline
(Tasks 1–3).

**Spec:** `docs/superpowers/specs/2026-08-27-filmes-do-fabrito-design.md`
(seções 4, 6.4, 7, 8, 12) e
`docs/superpowers/specs/2026-08-29-plano-2-decisoes-de-design.md` (as
decisões de design que preenchem as lacunas que o spec original deixou em
aberto — leia esse documento antes de começar, ele explica o *porquê* de
`offsets.json`, dos campos extras em `index.json`, e da hospedagem na raiz).

## Global Constraints

- Identificadores de domínio em português (`obterFileira`, `calcularOffsets`,
  `normalizarVibe`); nomes de campo JSON e de contrato (`id`, `title`, `s`,
  `sha`) ficam como o TMDB/GitHub os definem. Comentários, docstrings e
  mensagens de commit em português.
- **Sem framework, sem etapa de build.** Nenhum `package.json` com
  dependências de runtime. O único `package.json` do projeto
  (`site/package.json`) existe só para `{"type": "module"}`, para o Node
  tratar `.js` como ES module nos testes — não instala nada.
- Módulos de lógica pura (`store.js`, `motor.js`, `vibes.js`, `github.js`,
  `router.js`, `onboarding.js`) são testados com `node --test` — sem jsdom,
  sem mock de DOM. `ui.js` **não tem teste unitário** — verificação é visual,
  via a ferramenta de navegador (screenshot ou leitura da árvore de
  acessibilidade), documentada em cada task que a usa. Não tente forçar
  `jsdom` ou qualquer outra dependência de teste de DOM.
- Todo `fetch` do cliente usa caminho **relativo** (`../data/catalog.jsonl`,
  não `/data/catalog.jsonl`), porque o site é servido como GitHub Pages de
  projeto (`usuario.github.io/filmes-do-fabrito/`), com prefixo de caminho —
  caminho absoluto quebraria.
- Token do GitHub nunca aparece em nenhum arquivo commitado nem em teste
  automatizado — testes de `github.js` usam um token literal falso
  (`"tok_teste"`) e mockam `fetch` global.
- `site/data/` continua sendo saída de build do pipeline, não editada à mão
  — já está no `.gitignore`. Os arquivos NOVOS que o pipeline passa a gerar
  (`offsets.json`) entram nesse mesmo diretório e seguem a mesma regra.
- Extensões ao pipeline (Tasks 1–2) não podem quebrar nenhum dos 111 testes
  Python existentes.

---

### Task 1: `index.json` carrega pôster, diretor, elenco e idioma; novo `offsets.json`

Duas mudanças em `sync/build.py`, motivadas pelo documento de decisões
(seções 2, 3 e 7): a home/grade precisam de `poster_path` pra mostrar
pôster, e a ação "o que mais se parece com esse" na ficha precisa de
diretor/elenco/idioma pra replicar o cálculo de afinidade no cliente. Um
novo arquivo `offsets.json` dá ao cliente o intervalo de bytes de cada
filme dentro de `catalog.jsonl`, pra buscar só a linha necessária via HTTP
Range request.

**Files:**
- Modify: `sync/build.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `Movie` (com `poster_path`, `directors`, `cast`, `language`,
  já existentes no dataclass — ver `sync/catalog.py`), `Scoring`, `Shelf`,
  `Build`, todos já produzidos pelo Plano 1.
- Produces: `calcular_offsets(caminho: Path) -> dict[int, tuple[int, int]]`
  — lê um `catalog.jsonl` já escrito e devolve `{id: (inicio_byte,
  fim_byte_inclusive)}`. `escrever_site_data` passa a também escrever
  `site/data/offsets.json` — mesma assinatura pública de antes, sem
  parâmetro novo (o caminho do catálogo é derivado de `destino.parent /
  "data" / "catalog.jsonl"`, já que `destino` é sempre `raiz/site/data` e o
  catálogo sempre `raiz/data/catalog.jsonl`, ver `sync/cli.py:305,344`).

- [ ] **Step 1: Escrever os testes que falham**

Adicione ao final de `tests/test_build.py`:

```python
def test_index_carrega_poster_diretor_elenco_e_idioma(tmp_path: Path):
    filme = Movie(
        id=1, title="F1", year=2000, runtime=100, genres=(18,), keywords=(),
        vote_average=7.0, vote_count=1000, directors=(9339,), cast=(6384, 2975),
        language="en", track="acervo", theatrical=False, added="2026-08-27",
        poster_path="/matrix.jpg", overview="sinopse",
    )
    escrever_site_data(
        tmp_path, {1: filme}, _pontuacao({1: 0.5}), [], Build(6.0, 24)
    )
    dados = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    linha = dados["movies"][0]
    assert linha["p"] == "/matrix.jpg"
    assert linha["d"] == [9339]
    assert linha["c"] == [6384, 2975]
    assert linha["l"] == "en"
    # sinopse NUNCA vai pro index -- só pro catalog.jsonl (decisão #2 do
    # documento de design: uma sinopse por filme pesaria demais no índice).
    assert "ov" not in linha


def test_calcular_offsets_reproduz_a_linha_exata(tmp_path: Path):
    catalogo = tmp_path / "data" / "catalog.jsonl"
    catalogo.parent.mkdir(parents=True)
    filmes = [
        _filme(1, keywords=(900,)),
        _filme(2, keywords=(900, 901)),
        _filme(3),
    ]
    escrever_catalogo(catalogo, filmes)

    offsets = calcular_offsets(catalogo)

    bruto = catalogo.read_bytes()
    for filme in filmes:
        inicio, fim = offsets[filme.id]
        trecho = bruto[inicio : fim + 1]
        linha = json.loads(trecho.decode("utf-8"))
        assert linha["id"] == filme.id
        # a linha capturada termina em quebra de linha, como escrita
        assert trecho.endswith(b"\n")


def test_offsets_json_e_publicado_no_destino(tmp_path: Path):
    catalogo_dir = tmp_path / "data"
    catalogo_dir.mkdir()
    escrever_catalogo(catalogo_dir / "catalog.jsonl", [_filme(1), _filme(2)])

    site_dir = tmp_path / "site" / "data"
    escrever_site_data(
        site_dir, {1: _filme(1), 2: _filme(2)},
        _pontuacao({1: 0.5, 2: 0.5}), [], Build(6.0, 24),
    )

    offsets = json.loads((site_dir / "offsets.json").read_text(encoding="utf-8"))
    assert set(offsets.keys()) == {"1", "2"}
    assert len(offsets["1"]) == 2
```

Adicione os imports necessários no topo do arquivo, se ainda não estiverem
presentes:

```python
from sync.build import calcular_offsets
from sync.catalog import escrever_catalogo
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_build.py -v`
Expected: FAIL com `ImportError: cannot import name 'calcular_offsets'`

- [ ] **Step 3: Implementar `calcular_offsets` e estender `escrever_site_data`**

Em `sync/build.py`, adicione a função e ajuste o dicionário do índice e a
chamada de escrita:

```python
def calcular_offsets(caminho: Path) -> dict[int, tuple[int, int]]:
    """Lê catalog.jsonl e devolve, por id, o intervalo de bytes [inicio,
    fim] (fim inclusive) da linha daquele filme -- o mesmo intervalo que um
    header `Range: bytes=inicio-fim` HTTP busca. Cada linha é
    `json.dumps(row) + "\n"`; o offset é medido nos bytes UTF-8 do arquivo,
    não em caracteres, porque é isso que o servidor conta para o Range.
    """
    offsets: dict[int, tuple[int, int]] = {}
    posicao = 0
    with caminho.open("rb") as arquivo:
        for linha_bytes in arquivo:
            linha = json.loads(linha_bytes.decode("utf-8"))
            inicio = posicao
            fim = posicao + len(linha_bytes) - 1
            offsets[linha["id"]] = (inicio, fim)
            posicao += len(linha_bytes)
    return offsets
```

Na função `escrever_site_data`, dentro do dicionário de cada filme do
índice, adicione as quatro chaves depois de `"th"`:

```python
                "th": f.theatrical,
                "p": f.poster_path,
                "d": list(f.directors),
                "c": list(f.cast),
                "l": f.language,
```

E, depois do bloco que escreve `keywords.json`, adicione a escrita de
`offsets.json`, derivando o caminho do catálogo a partir de `destino`:

```python
    caminho_catalogo = destino.parent.parent / "data" / "catalog.jsonl"
    offsets = calcular_offsets(caminho_catalogo)
    _escrever(
        destino / "offsets.json",
        {str(id_): [inicio, fim] for id_, (inicio, fim) in sorted(offsets.items())},
    )
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `.venv/Scripts/pytest tests/test_build.py -v`
Expected: PASS, todos os testes do arquivo

- [ ] **Step 5: Rodar a suíte inteira**

Run: `.venv/Scripts/pytest -q`
Expected: PASS, nenhum dos 111 testes anteriores quebrado

- [ ] **Step 6: Commit**

```bash
git add sync/build.py tests/test_build.py
git commit -m "feat: index.json carrega poster/diretor/elenco/idioma; novo offsets.json"
```

---

### Task 2: Nomes de keyword persistidos em `data/nomes.json`

O nome de cada keyword já chega na mesma resposta de `/movie/{id}` que o
pipeline usa pra pegar o id, e hoje é descartado. Estende `nomes.json` com
um terceiro balde `"keyword"`, sem nenhuma chamada de API a mais.

**Files:**
- Modify: `sync/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `detalhe["keywords"]["keywords"]` (lista de `{"id":int,
  "name":str}`), já disponível no loop de `executar` em `sync/cli.py`.
- Produces: `_carregar_nomes`/`_escrever_nomes` passam a incluir a chave
  `"keyword"` no dicionário, ao lado de `"director"`/`"cast"` já
  existentes. Assinaturas inalteradas.

- [ ] **Step 1: Escrever o teste que falha**

Adicione a `tests/test_cli.py` (reaproveite os helpers já existentes no
arquivo, como o cliente TMDB mockado e o `tmp_path` com `config.json`
copiado — siga o padrão dos testes de `executar` já presentes):

```python
@respx.mock
async def test_nomes_de_keyword_sao_persistidos(tmp_path, config_copiado):
    raiz = tmp_path
    detalhe_filme = {
        "id": 42,
        "title": "F42",
        "release_date": "2020-01-01",
        "runtime": 100,
        "vote_count": 100,
        "genres": [],
        "keywords": {"keywords": [{"id": 900, "name": "vinganca"}]},
        "credits": {"cast": [], "crew": []},
        "release_dates": {"results": []},
    }
    respx.get(url__regex=r".*/movie/42$").mock(
        return_value=httpx.Response(200, json=detalhe_filme)
    )
    respx.get(url__regex=r".*files\.tmdb\.org.*").mock(
        return_value=httpx.Response(404)
    )

    await executar(
        raiz=raiz, token="tok", hoje=date(2026, 8, 29), carga_inicial=True
    )

    nomes = json.loads((raiz / "data" / "nomes.json").read_text(encoding="utf-8"))
    assert nomes["keyword"]["900"] == "vinganca"
```

Se o arquivo de testes não tiver um fixture pronto para `carga_inicial=True`
com mocks completos de `descobrir_fatiado`, adapte o teste acima ao padrão
real já usado pelos outros testes de `executar` nesse arquivo — o essencial
verificado é: depois de `executar`, `data/nomes.json` tem a chave
`"keyword"` com o id da keyword mapeado pro nome que veio na resposta da
API.

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv/Scripts/pytest tests/test_cli.py -k keyword -v`
Expected: FAIL — `nomes["keyword"]` levanta `KeyError` (a chave não existe
ainda)

- [ ] **Step 3: Implementar**

Em `sync/cli.py`, em `_carregar_nomes`, adicione o terceiro balde:

```python
def _carregar_nomes(raiz: Path) -> dict[str, dict[int, str]]:
    caminho = raiz / "data" / "nomes.json"
    if not caminho.exists():
        return {"director": {}, "cast": {}, "keyword": {}}

    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return {
        "director": {int(k): v for k, v in (bruto.get("director") or {}).items()},
        "cast": {int(k): v for k, v in (bruto.get("cast") or {}).items()},
        "keyword": {int(k): v for k, v in (bruto.get("keyword") or {}).items()},
    }
```

No loop de `executar` que já popula `nomes["director"]`/`nomes["cast"]`
(logo depois de `catalogo[filme.id] = filme`), adicione a extração das
keywords do mesmo `detalhe`:

```python
        creditos = detalhe.get("credits") or {}
        for pessoa in creditos.get("crew") or []:
            if pessoa.get("job") == "Director":
                nomes["director"][pessoa["id"]] = pessoa.get("name", "")
        for pessoa in (creditos.get("cast") or [])[:5]:
            nomes["cast"][pessoa["id"]] = pessoa.get("name", "")
        palavras = (detalhe.get("keywords") or {}).get("keywords") or []
        for palavra in palavras:
            nomes["keyword"][palavra["id"]] = palavra.get("name", "")
```

`_escrever_nomes` já serializa o dicionário genericamente (itera
`nomes.items()`), então não precisa de mudança — a chave nova passa
automaticamente.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/pytest tests/test_cli.py -v`
Expected: PASS, incluindo o teste novo e todos os anteriores do arquivo

- [ ] **Step 5: Rodar a suíte inteira**

Run: `.venv/Scripts/pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add sync/cli.py tests/test_cli.py
git commit -m "feat: persiste nomes de keyword em data/nomes.json"
```

---

### Task 3: `data/generos.json` — lista oficial de gêneros em pt-BR

Uma lista pequena e estável (~19 gêneros), buscada uma vez na API do TMDB e
commitada como dado estático — não é responsabilidade do pipeline diário,
não muda quase nunca.

**Files:**
- Create: `scripts/gerar_generos.py`
- Create: `data/generos.json` (gerado pelo script, depois commitado)

**Interfaces:**
- Consumes: `TMDB_TOKEN` do ambiente.
- Produces: `data/generos.json` no formato `{"<id>": "Nome em pt-BR", ...}`.

- [ ] **Step 1: Escrever o script gerador**

Siga o padrão de `scripts/gerar_vibes.py` (já existe no repositório —
leia-o antes de escrever este, para manter o mesmo estilo de cliente HTTP
e tratamento de erro):

```python
"""Gera data/generos.json a partir da lista oficial de generos do TMDB.

Executado uma vez, manualmente. Nao faz parte do pipeline diario -- a lista
de generos do TMDB e pequena (~19 itens) e praticamente nunca muda.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent


def buscar_generos(token: str) -> dict[str, str]:
    resposta = httpx.get(
        "https://api.themoviedb.org/3/genre/movie/list",
        params={"language": "pt-BR"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    return {str(g["id"]): g["name"] for g in dados["genres"]}


def main() -> None:
    token = os.environ.get("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN nao esta definido no ambiente")

    generos = buscar_generos(token)
    destino = RAIZ / "data" / "generos.json"
    destino.write_text(
        json.dumps(generos, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    print(f"{len(generos)} generos escritos em {destino}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar o script**

Run: `.venv/Scripts/python scripts/gerar_generos.py`
Expected: imprime `19 generos escritos em .../data/generos.json` (o número
exato pode variar ligeiramente conforme o TMDB atualize a lista, mas fica
na casa de 19)

- [ ] **Step 3: Conferir o conteúdo**

Leia `data/generos.json` e confirme que tem entradas plausíveis como
`"18": "Drama"`, `"28": "Ação"`, `"27": "Terror"`. Se algum nome vier em
inglês ou vazio, o parâmetro `language=pt-BR` não foi aplicado — não
prossiga sem isso estar correto, porque é exatamente o dado que a grade usa
como rótulo de filtro.

- [ ] **Step 4: Commit**

```bash
git add scripts/gerar_generos.py data/generos.json
git commit -m "feat: adiciona data/generos.json com a lista oficial em pt-BR"
```

---

### Task 4: Esqueleto do site — `index.html`, `style.css`, atribuição do TMDB

A casca estática das três telas (home, grade, ficha), escondidas/mostradas
por classe CSS, mais o rodapé de atribuição obrigatória com o logo real do
TMDB.

**Files:**
- Create: `site/index.html`
- Create: `site/style.css`
- Create: `site/assets/tmdb-logo.svg`

**Interfaces:**
- Consumes: nada ainda (JS vem nas próximas tasks).
- Produces: a estrutura DOM que `site/js/ui.js` (Task 7 em diante) vai
  preencher — três `<section>` com ids `tela-home`, `tela-grade`,
  `tela-ficha`, mais um `<div id="onboarding">` para a Task 15. Classe
  `.oculto { display: none; }` controla qual tela aparece.

- [ ] **Step 1: Buscar o logo oficial do TMDB**

Use a ferramenta de navegador para abrir
`https://www.themoviedb.org/about/logos-attribution` e salvar localmente o
SVG do logo azul curto ("short blue") oferecido ali pela própria página de
atribuição do TMDB. Salve o arquivo em `site/assets/tmdb-logo.svg`. Se o
site mudar de estrutura e o logo não for encontrável diretamente, baixe
qualquer uma das variantes SVG oficiais disponibilizadas nessa mesma página
— o requisito do spec é ter *o* logo, não uma variante específica.

- [ ] **Step 2: Escrever `site/index.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Filmes do Fabrito</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="cabecalho">
    <a href="#/" class="logo-app">Filmes do Fabrito</a>
    <input type="search" id="busca-vibe" placeholder="Busque por vibe: fim do mundo, assalto, luto..." />
  </header>

  <main id="app">
    <section id="tela-home" class="tela oculto">
      <div id="lista-fileiras"></div>
    </section>

    <section id="tela-grade" class="tela oculto">
      <div class="grade-cabecalho">
        <h2 id="grade-titulo"></h2>
        <div class="grade-filtros">
          <select id="filtro-genero"><option value="">Gênero</option></select>
          <select id="filtro-decada"><option value="">Década</option></select>
          <select id="filtro-duracao">
            <option value="">Duração</option>
            <option value="curto">Até 100 min</option>
            <option value="longo">Mais de 100 min</option>
          </select>
          <select id="filtro-visto">
            <option value="">Visto?</option>
            <option value="nao-visto">Só não vistos</option>
            <option value="visto">Só vistos</option>
          </select>
        </div>
      </div>
      <div id="grade-posteres" class="grade-posteres"></div>
    </section>

    <section id="tela-ficha" class="tela oculto">
      <div id="ficha-conteudo"></div>
    </section>

    <section id="onboarding" class="tela oculto">
      <h2>Antes de começar</h2>
      <p>Marque rapidamente o que você já viu, gostou ou não gostou. Isso treina o motor de recomendação.</p>
      <div id="onboarding-cartoes"></div>
    </section>
  </main>

  <footer class="rodape-atribuicao">
    <img src="assets/tmdb-logo.svg" alt="TMDB" class="logo-tmdb" />
    <p>Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB.</p>
  </footer>

  <script type="module" src="js/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Escrever `site/style.css`**

Um CSS enxuto, mobile-first, tema escuro (combina com pôster de filme).
Não precisa ser extenso nesta task — as próximas tasks adicionam classes
específicas de cada tela conforme necessário. O essencial agora:

```css
* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0f0f12;
  --bg-elevado: #1a1a1f;
  --texto: #ececec;
  --texto-fraco: #9a9aa3;
  --acento: #e8b84b;
  --borda: #2a2a30;
}

body {
  background: var(--bg);
  color: var(--texto);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.oculto { display: none !important; }

.cabecalho {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--borda);
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 10;
}

.logo-app {
  color: var(--acento);
  font-weight: 700;
  text-decoration: none;
  font-size: 1.1rem;
  white-space: nowrap;
}

#busca-vibe {
  flex: 1;
  max-width: 420px;
  background: var(--bg-elevado);
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 8px 12px;
  color: var(--texto);
}

main { flex: 1; padding: 16px 20px 40px; }

.rodape-atribuicao {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--borda);
  color: var(--texto-fraco);
  font-size: 0.75rem;
}

.logo-tmdb { height: 16px; width: auto; }
```

- [ ] **Step 4: Verificar visualmente**

Use a ferramenta de navegador (`preview_start` apontando pra um servidor
estático simples servindo a pasta `site/`, ou abra o arquivo direto) para
confirmar que a página carrega sem erro no console, o cabeçalho e o rodapé
aparecem, e o logo do TMDB renderiza (não aparece ícone de imagem quebrada).

- [ ] **Step 5: Commit**

```bash
git add site/index.html site/style.css site/assets/tmdb-logo.svg
git commit -m "feat: esqueleto do site com atribuicao do TMDB"
```

---

### Task 5: `site/js/store.js` — carregamento e cache dos dados

A camada que busca `index.json`/`shelves.json` uma vez, guarda em memória, e
expõe funções de consulta que o resto do site usa. Ninguém além deste
módulo faz `fetch` de `index.json`/`shelves.json`.

**Files:**
- Create: `site/js/store.js`
- Test: `site/js/store.test.js`
- Create: `site/package.json`

**Interfaces:**
- Consumes: `../data/index.json`, `../data/shelves.json` (caminho relativo
  a partir de `site/js/`, ou seja `site/data/index.json` de fato).
- Produces:
  - `async function carregarCatalogo() -> {movies: Array<Filme>}` (cacheado
    após a primeira chamada; chamadas seguintes devolvem o mesmo objeto sem
    novo fetch)
  - `async function carregarFileiras() -> {shelves: Array<Fileira>}`
    (idem, cacheado)
  - `function obterFilme(id: number) -> Filme | undefined` (busca no
    catálogo já carregado; lança se chamado antes de `carregarCatalogo`)
  - `function filtrarGrade(filmes: Array<Filme>, filtros: {genero,
    decada, duracao, visto, idsVistos: Set<number>, vibeIds?: number[] | null}) -> Array<Filme>`
    — `vibeIds`, quando presente, exige que o filme tenha ao menos uma das
    keywords da lista (usado pela busca por vibe do cabeçalho, Task 10).
  - `function _resetarCacheParaTeste()` — só para os testes zerarem o
    cache do módulo entre casos.

- [ ] **Step 1: Criar `site/package.json`**

```json
{
  "type": "module"
}
```

- [ ] **Step 2: Escrever os testes que falham**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  carregarCatalogo,
  obterFilme,
  filtrarGrade,
  _resetarCacheParaTeste,
} from "./store.js";

function mockFetch(respostas) {
  globalThis.fetch = async (url) => {
    const chave = Object.keys(respostas).find((k) => url.includes(k));
    if (!chave) throw new Error(`fetch nao mockado para ${url}`);
    return {
      ok: true,
      status: 200,
      json: async () => respostas[chave],
    };
  };
}

test("carregarCatalogo busca uma vez e cacheia", async () => {
  _resetarCacheParaTeste();
  let chamadas = 0;
  globalThis.fetch = async () => {
    chamadas++;
    return { ok: true, status: 200, json: async () => ({ movies: [{ id: 1, t: "F1" }] }) };
  };

  await carregarCatalogo();
  await carregarCatalogo();

  assert.equal(chamadas, 1);
});

test("obterFilme encontra pelo id apos carregar", async () => {
  _resetarCacheParaTeste();
  mockFetch({ "index.json": { movies: [{ id: 603, t: "Matrix", y: 1999 }] } });

  await carregarCatalogo();

  assert.deepEqual(obterFilme(603), { id: 603, t: "Matrix", y: 1999 });
  assert.equal(obterFilme(999), undefined);
});

test("filtrarGrade combina genero, decada, duracao e visto", () => {
  const filmes = [
    { id: 1, y: 1999, r: 90, g: [28] },
    { id: 2, y: 1999, r: 150, g: [18] },
    { id: 3, y: 2020, r: 90, g: [28] },
  ];

  const soAcao90s = filtrarGrade(filmes, {
    genero: 28, decada: 1990, duracao: "", visto: "", idsVistos: new Set(),
  });
  assert.deepEqual(soAcao90s.map((f) => f.id), [1]);

  const soCurto = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "curto", visto: "", idsVistos: new Set(),
  });
  assert.deepEqual(soCurto.map((f) => f.id).sort(), [1, 3]);

  const soNaoVistos = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "", visto: "nao-visto", idsVistos: new Set([1]),
  });
  assert.deepEqual(soNaoVistos.map((f) => f.id).sort(), [2, 3]);
});

test("filtrarGrade sem nenhum filtro devolve tudo", () => {
  const filmes = [{ id: 1, y: 2000, r: 100, g: [1] }];
  const resultado = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "", visto: "", idsVistos: new Set(),
  });
  assert.equal(resultado.length, 1);
});

test("filtrarGrade com vibeIds exige interseccao de keywords", () => {
  const filmes = [
    { id: 1, y: 2000, r: 100, g: [1], k: [900] },
    { id: 2, y: 2000, r: 100, g: [1], k: [901] },
    { id: 3, y: 2000, r: 100, g: [1], k: [] },
  ];
  const resultado = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "", visto: "", idsVistos: new Set(),
    vibeIds: [900, 950],
  });
  assert.deepEqual(resultado.map((f) => f.id), [1]);
});
```

- [ ] **Step 3: Rodar e confirmar a falha**

Run: `cd site && node --test js/store.test.js`
Expected: FAIL — `Cannot find module './store.js'`

- [ ] **Step 4: Implementar `site/js/store.js`**

```javascript
// Camada de acesso a dados: busca index.json/shelves.json uma vez, cacheia
// em memória, e expõe consultas. Nenhum outro módulo faz fetch desses dois
// arquivos diretamente -- é este módulo, e só ele, que sabe o caminho.

const CAMINHO_INDICE = "../data/index.json";
const CAMINHO_FILEIRAS = "../data/shelves.json";

let _catalogoCache = null;
let _fileirasCache = null;
let _porId = null;

export async function carregarCatalogo() {
  if (_catalogoCache) return _catalogoCache;

  const resposta = await fetch(CAMINHO_INDICE);
  if (!resposta.ok) {
    throw new Error(`falha ao carregar index.json: ${resposta.status}`);
  }
  _catalogoCache = await resposta.json();
  _porId = new Map(_catalogoCache.movies.map((f) => [f.id, f]));
  return _catalogoCache;
}

export async function carregarFileiras() {
  if (_fileirasCache) return _fileirasCache;

  const resposta = await fetch(CAMINHO_FILEIRAS);
  if (!resposta.ok) {
    throw new Error(`falha ao carregar shelves.json: ${resposta.status}`);
  }
  _fileirasCache = await resposta.json();
  return _fileirasCache;
}

export function obterFilme(id) {
  if (!_porId) {
    throw new Error("obterFilme chamado antes de carregarCatalogo()");
  }
  return _porId.get(id);
}

function decadaDe(filme) {
  return filme.y ? Math.floor(filme.y / 10) * 10 : null;
}

export function filtrarGrade(filmes, filtros) {
  const { genero, decada, duracao, visto, idsVistos, vibeIds } = filtros;
  const vibeSet = vibeIds ? new Set(vibeIds) : null;

  return filmes.filter((f) => {
    if (genero && !f.g.includes(Number(genero))) return false;
    if (decada && decadaDe(f) !== Number(decada)) return false;
    if (duracao === "curto" && f.r >= 100) return false;
    if (duracao === "longo" && f.r < 100) return false;
    if (visto === "visto" && !idsVistos.has(f.id)) return false;
    if (visto === "nao-visto" && idsVistos.has(f.id)) return false;
    if (vibeSet && !(f.k || []).some((id) => vibeSet.has(id))) return false;
    return true;
  });
}

export function _resetarCacheParaTeste() {
  _catalogoCache = null;
  _fileirasCache = null;
  _porId = null;
}
```

- [ ] **Step 5: Rodar e confirmar que passam**

Run: `cd site && node --test js/store.test.js`
Expected: PASS, 5 testes

- [ ] **Step 6: Commit**

```bash
git add site/package.json site/js/store.js site/js/store.test.js
git commit -m "feat: camada de dados do site (store.js)"
```

---

### Task 6: Roteamento por hash e bootstrap (`router.js` + `app.js`)

Um roteador mínimo: lê `location.hash`, decide qual tela mostrar. `app.js`
é o ponto de entrada que liga tudo.

**Files:**
- Create: `site/js/router.js`
- Test: `site/js/router.test.js`
- Create: `site/js/app.js`

**Interfaces:**
- Consumes: `carregarCatalogo`, `carregarFileiras` de `store.js`.
- Produces:
  - `function analisarHash(hash: string) -> {tela: "home"|"grade"|"ficha", parametro?: string|number, vibe?: string}`
    — `vibe` só aparece quando a URL carrega `?vibe=<texto>` (usado pela
    busca por vibe do cabeçalho, ligada na Task 10).
  - `function navegarPara(hash: string) -> void` (seta `location.hash`)
  - `function iniciarRoteador(aoMudarRota: (rota) => void) -> void` —
    registra o listener de `hashchange` e dispara a rota inicial uma vez.

- [ ] **Step 1: Escrever os testes que falham**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { analisarHash } from "./router.js";

test("hash vazio ou so # e a home", () => {
  assert.deepEqual(analisarHash(""), { tela: "home" });
  assert.deepEqual(analisarHash("#"), { tela: "home" });
  assert.deepEqual(analisarHash("#/"), { tela: "home" });
});

test("grade sem fileira e o modo explorar geral", () => {
  assert.deepEqual(analisarHash("#/grade"), { tela: "grade", parametro: null });
});

test("grade com chave de fileira", () => {
  assert.deepEqual(analisarHash("#/grade/classicos"), {
    tela: "grade", parametro: "classicos",
  });
});

test("ficha com id numerico", () => {
  assert.deepEqual(analisarHash("#/filme/603"), {
    tela: "ficha", parametro: 603,
  });
});

test("hash desconhecido cai para home", () => {
  assert.deepEqual(analisarHash("#/qualquer-coisa"), { tela: "home" });
});

test("grade com query de vibe", () => {
  assert.deepEqual(analisarHash("#/grade?vibe=fim%20do%20mundo"), {
    tela: "grade", parametro: null, vibe: "fim do mundo",
  });
});

test("grade com fileira nao tem vibe quando a query nao existe", () => {
  const rota = analisarHash("#/grade/classicos");
  assert.equal("vibe" in rota, false);
});
```

`router.js` manipula `location`/`window`, que não existem no Node — por
isso os testes acima cobrem só `analisarHash` (função pura, sem DOM).
`navegarPara`/`iniciarRoteador` não têm teste unitário; são verificados
visualmente na Task 7, quando a home já estiver de pé.

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/router.test.js`
Expected: FAIL — `Cannot find module './router.js'`

- [ ] **Step 3: Implementar `site/js/router.js`**

```javascript
// Roteador por hash. Formatos:
//   #/                        -> home
//   #/grade                   -> grade explorando o catálogo inteiro
//   #/grade/<chave>           -> grade mostrando os ids daquela fileira
//   #/grade?vibe=<texto>      -> grade filtrada pela busca do cabeçalho
//   #/filme/<id>              -> ficha do filme

export function analisarHash(hash) {
  const bruto = hash || "";
  const [semQuery, query] = bruto.split("?");
  const limpo = semQuery.replace(/^#\/?/, "");

  if (!limpo) return { tela: "home" };

  const partes = limpo.split("/").filter(Boolean);

  if (partes[0] === "grade") {
    const rota = { tela: "grade", parametro: partes[1] ?? null };
    if (query) {
      const parametros = new URLSearchParams(query);
      const vibe = parametros.get("vibe");
      if (vibe) rota.vibe = vibe;
    }
    return rota;
  }
  if (partes[0] === "filme" && partes[1]) {
    const id = Number(partes[1]);
    if (!Number.isNaN(id)) return { tela: "ficha", parametro: id };
  }

  return { tela: "home" };
}

export function navegarPara(hash) {
  window.location.hash = hash;
}

export function iniciarRoteador(aoMudarRota) {
  const disparar = () => aoMudarRota(analisarHash(window.location.hash));
  window.addEventListener("hashchange", disparar);
  disparar();
}
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/router.test.js`
Expected: PASS, 7 testes

- [ ] **Step 5: Escrever `site/js/app.js`**

Ponto de entrada mínimo por enquanto — só troca qual `<section>` fica
visível. As próximas tasks preenchem o conteúdo de cada tela.

```javascript
import { iniciarRoteador } from "./router.js";
import { carregarCatalogo, carregarFileiras } from "./store.js";

const TELAS = {
  home: document.getElementById("tela-home"),
  grade: document.getElementById("tela-grade"),
  ficha: document.getElementById("tela-ficha"),
};

function mostrarTela(nome) {
  for (const [chave, elemento] of Object.entries(TELAS)) {
    elemento.classList.toggle("oculto", chave !== nome);
  }
}

async function aoMudarRota(rota) {
  mostrarTela(rota.tela);
  // Cada tela específica (home/grade/ficha) é preenchida nas próximas
  // tasks -- por ora só a troca de visibilidade já é verificável.
}

async function iniciar() {
  await Promise.all([carregarCatalogo(), carregarFileiras()]);
  iniciarRoteador(aoMudarRota);
}

iniciar();
```

- [ ] **Step 6: Verificar visualmente**

Sirva `site/` localmente (`preview_start`) e navegue para `#/grade` e
`#/filme/1` diretamente na barra de endereço — confirme, pela árvore de
acessibilidade, que a seção correspondente perde a classe `oculto` e as
outras duas mantêm.

- [ ] **Step 7: Commit**

```bash
git add site/js/router.js site/js/router.test.js site/js/app.js
git commit -m "feat: roteamento por hash e bootstrap do app"
```

---

### Task 7: `site/js/motor.js` — porta do motor de pontuação para "similar"

Fiel a `sync/score.py`/`sync/profile.py`, para a ação "o que mais se parece
com esse" da ficha (Task 11) funcionar sem servidor. Ver seção 7 do
documento de decisões — é lógica pura, standalone, então entra antes das
telas que a usam.

**Files:**
- Create: `site/js/motor.js`
- Test: `site/js/motor.test.js`

**Interfaces:**
- Consumes: `Array<Filme>` no formato de `index.json` (precisa dos campos
  `g,k,d,c,l,y` — todos publicados desde a Task 1), e o objeto de pesos do
  `config.json` (`{keyword,director,cast,genre,decade,language}`).
- Produces:
  - `function featuresDe(filme) -> {keyword: number[], director: number[], cast: number[], genre: number[], decade: number[], language: string[]}`
  - `function construirGostoDeUmFilme(filme, catalogo, pesos, k=2.0) -> Map<string, number>`
    (chave `"tipo:valor"`, valor = peso)
  - `function afinidade(filme, gosto, pesos) -> number`
  - `function filmesSimilares(filmeReferencia, catalogo, pesos, pesoAfinidade, limite=24) -> Array<{id, score}>`
    (exclui o próprio filme de referência; ordena por score desc)

- [ ] **Step 1: Escrever os testes que falham**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  featuresDe,
  construirGostoDeUmFilme,
  afinidade,
  filmesSimilares,
} from "./motor.js";

const PESOS = { keyword: 0.4, director: 0.2, cast: 0.15, genre: 0.15, decade: 0.06, language: 0.04 };

function filme(id, extra = {}) {
  return { id, y: 2000, g: [], k: [], d: [], c: [], l: "en", ...extra };
}

test("featuresDe deriva a decada do ano", () => {
  assert.deepEqual(featuresDe(filme(1, { y: 1999 })).decade, [1990]);
  assert.deepEqual(featuresDe(filme(2, { y: null })).decade, []);
});

test("caracteristica rara pesa mais que a comum", () => {
  // 'comum' esta em todos os 10 filmes do catalogo; 'rara' so no filme 1.
  const catalogo = new Map();
  for (let i = 1; i <= 10; i++) catalogo.set(i, filme(i, { k: [100] }));
  catalogo.set(1, filme(1, { k: [100, 200] }));

  const gosto = construirGostoDeUmFilme(catalogo.get(1), catalogo, PESOS);

  assert.ok(gosto.get("keyword:200") > gosto.get("keyword:100"));
});

test("afinidade e 1.0 quando todas as caracteristicas do filme batem com o gosto", () => {
  const gosto = new Map([["genre:18", 1.0]]);
  assert.equal(afinidade(filme(1, { g: [18] }), gosto, PESOS), 1.0);
});

test("afinidade e 0 quando nenhuma caracteristica e conhecida", () => {
  const gosto = new Map([["genre:99", 1.0]]);
  assert.equal(afinidade(filme(1, { g: [18] }), gosto, PESOS), 0);
});

test("filmesSimilares exclui o proprio filme de referencia e ordena por score", () => {
  const catalogo = new Map();
  for (let i = 1; i <= 5; i++) catalogo.set(i, filme(i, { g: [18] }));
  catalogo.set(3, filme(3, { g: [99] })); // o menos parecido

  const referencia = catalogo.get(1);
  const resultado = filmesSimilares(referencia, catalogo, PESOS, 0.75, 10);

  assert.ok(!resultado.some((r) => r.id === 1));
  assert.ok(resultado.length > 0);
  for (let i = 1; i < resultado.length; i++) {
    assert.ok(resultado[i - 1].score >= resultado[i].score);
  }
});
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/motor.test.js`
Expected: FAIL — `Cannot find module './motor.js'`

- [ ] **Step 3: Implementar `site/js/motor.js`**

```javascript
// Porta fiel de sync/score.py + sync/profile.py, para a ficha do filme
// poder calcular "o que mais se parece com esse" sem servidor -- ver
// documento de decisões do Plano 2, seção 7. Mesma fórmula, mesmos pesos.

function decadaDe(filme) {
  return filme.y ? Math.floor(filme.y / 10) * 10 : null;
}

export function featuresDe(filme) {
  return {
    keyword: filme.k || [],
    director: filme.d || [],
    cast: filme.c || [],
    genre: filme.g || [],
    decade: filme.y ? [decadaDe(filme)] : [],
    language: filme.l ? [filme.l] : [],
  };
}

function frequenciaNoCatalogo(catalogo) {
  const freq = new Map();
  for (const filme of catalogo.values()) {
    const features = featuresDe(filme);
    for (const [tipo, valores] of Object.entries(features)) {
      for (const valor of new Set(valores)) {
        const chave = `${tipo}:${valor}`;
        freq.set(chave, (freq.get(chave) || 0) + 1);
      }
    }
  }
  return freq;
}

// Constrói o vetor de gosto a partir de UM filme (positivo) contra o
// catálogo inteiro -- mesma suavização e mesmo idf que o pipeline usa em
// gosto_de_um_filme / construir_gosto (sync/profile.py).
export function construirGostoDeUmFilme(filmeReferencia, catalogo, pesos, k = 2.0) {
  const freq = frequenciaNoCatalogo(catalogo);
  const total = Math.max(catalogo.size, 1);
  const gosto = new Map();

  const features = featuresDe(filmeReferencia);
  for (const [tipo, valores] of Object.entries(features)) {
    for (const valor of new Set(valores)) {
      const chave = `${tipo}:${valor}`;
      const p = 1;
      const n = 0;
      const afin = (p - n) / (p + n + k);
      const idf = Math.log(total / (1 + (freq.get(chave) || 0)));
      gosto.set(chave, afin * idf);
    }
  }
  return gosto;
}

export function afinidade(filme, gosto, pesos) {
  const features = featuresDe(filme);
  const presentes = {};

  for (const [tipo, valores] of Object.entries(features)) {
    const unicos = new Set(valores);
    if (unicos.size === 0) continue;
    let soma = 0;
    for (const valor of unicos) soma += gosto.get(`${tipo}:${valor}`) || 0;
    presentes[tipo] = soma / unicos.size;
  }

  const tipos = Object.keys(presentes);
  if (tipos.length === 0) return 0;

  const totalPeso = tipos.reduce((acc, t) => acc + (pesos[t] || 0), 0);
  if (totalPeso === 0) return 0;

  return tipos.reduce(
    (acc, t) => acc + (pesos[t] / totalPeso) * presentes[t], 0
  );
}

// Sem uma âncora de qualidade separada disponível no cliente (index.json
// só publica o score final já misturado, não afinidade/qualidade
// separadas), usamos só a afinidade normalizada entre os candidatos como
// critério de ordenação -- diferente da fileira "similar" do próprio
// pipeline, que tem acesso à qualidade bayesiana calculada no servidor.
export function filmesSimilares(filmeReferencia, catalogo, pesos, pesoAfinidade, limite = 24) {
  const gosto = construirGostoDeUmFilme(filmeReferencia, catalogo, pesos);
  const candidatos = [...catalogo.values()].filter((f) => f.id !== filmeReferencia.id);

  const pontuados = candidatos.map((f) => ({
    id: f.id,
    afinidade: afinidade(f, gosto, pesos),
  }));

  const valores = pontuados.map((p) => p.afinidade);
  const menor = Math.min(...valores);
  const maior = Math.max(...valores);
  const amplitude = maior - menor;

  const comScore = pontuados.map((p) => ({
    id: p.id,
    score: amplitude > 1e-12 ? (p.afinidade - menor) / amplitude : 0,
  }));

  comScore.sort((a, b) => b.score - a.score);
  return comScore.slice(0, limite);
}
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/motor.test.js`
Expected: PASS, 5 testes

- [ ] **Step 5: Commit**

```bash
git add site/js/motor.js site/js/motor.test.js
git commit -m "feat: porta do motor de pontuacao para 'o que mais se parece com esse'"
```

---

### Task 8: `site/js/vibes.js` — normalização e busca por vibe

Casa o texto digitado (com ou sem acento) contra as chaves de `vibes.json`
(hoje sem acento — ver documento de decisões, isso funciona nos dois casos
porque normaliza dos dois lados).

**Files:**
- Create: `site/js/vibes.js`
- Test: `site/js/vibes.test.js`

**Interfaces:**
- Consumes: `../data/vibes.json` (formato `{"expressao": [keyword_id, ...]}`).
- Produces:
  - `function normalizarTexto(texto: string) -> string` (minúsculo, sem
    acento, sem espaço nas pontas)
  - `async function carregarVibes() -> Map<string_normalizada, number[]>`
    (cacheado)
  - `function buscarVibe(consulta: string, vibesCarregadas: Map) -> number[] | null`
    (match exato pós-normalização; devolve `null` se não achar)

- [ ] **Step 1: Escrever os testes que falham**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizarTexto, buscarVibe } from "./vibes.js";

test("normalizarTexto remove acento e caixa", () => {
  assert.equal(normalizarTexto("Vingança"), "vinganca");
  assert.equal(normalizarTexto("  Fim do Mundo  "), "fim do mundo");
  assert.equal(normalizarTexto("esperança"), "esperanca");
});

test("buscarVibe encontra com ou sem acento na consulta", () => {
  const vibes = new Map([["vinganca", [900, 901]]]);
  assert.deepEqual(buscarVibe("vingança", vibes), [900, 901]);
  assert.deepEqual(buscarVibe("VINGANCA", vibes), [900, 901]);
  assert.equal(buscarVibe("algo que nao existe", vibes), null);
});
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/vibes.test.js`
Expected: FAIL — `Cannot find module './vibes.js'`

- [ ] **Step 3: Implementar `site/js/vibes.js`**

```javascript
// vibes.json tem chaves sem acento (herdado da primeira versão do
// dicionário). Normalizar dos dois lados -- a chave armazenada e a
// consulta digitada -- faz o casamento funcionar hoje e continuar
// funcionando se as chaves forem re-acentuadas no futuro.

const CAMINHO_VIBES = "../data/vibes.json";

let _vibesCache = null;

export function normalizarTexto(texto) {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export async function carregarVibes() {
  if (_vibesCache) return _vibesCache;

  const resposta = await fetch(CAMINHO_VIBES);
  if (!resposta.ok) {
    throw new Error(`falha ao carregar vibes.json: ${resposta.status}`);
  }
  const bruto = await resposta.json();

  _vibesCache = new Map(
    Object.entries(bruto).map(([chave, ids]) => [normalizarTexto(chave), ids])
  );
  return _vibesCache;
}

export function buscarVibe(consulta, vibesCarregadas) {
  const chave = normalizarTexto(consulta);
  return vibesCarregadas.get(chave) ?? null;
}
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/vibes.test.js`
Expected: PASS, 2 testes

- [ ] **Step 5: Commit**

```bash
git add site/js/vibes.js site/js/vibes.test.js
git commit -m "feat: normalizacao e busca por vibe"
```

---

### Task 9: Tela Home — fileiras

Preenche `#lista-fileiras` com as fileiras de `shelves.json`, pôster a
pôster, na ordem publicada. Clique no título abre a grade daquela fileira;
clique no pôster abre a ficha.

**Files:**
- Create: `site/js/ui.js`
- Modify: `site/js/app.js`
- Modify: `site/style.css`

**Interfaces:**
- Consumes: `carregarFileiras`, `obterFilme` de `store.js`;
  `navegarPara` de `router.js`.
- Produces: `function renderizarHome(fileiras: Array<Fileira>) -> void`
  (escreve direto no DOM, sem retorno).

- [ ] **Step 1: Implementar `renderizarHome` em `site/js/ui.js`**

Sem teste unitário (módulo de DOM, ver Global Constraints) — a verificação
é o Step 2, visual.

```javascript
import { obterFilme } from "./store.js";

const URL_POSTER = "https://image.tmdb.org/t/p/w185";

function elementoPoster(id) {
  const filme = obterFilme(id);
  const div = document.createElement("a");
  div.href = `#/filme/${id}`;
  div.className = "poster";
  if (!filme) {
    div.textContent = "?";
    return div;
  }
  const img = document.createElement("img");
  img.src = filme.p ? `${URL_POSTER}${filme.p}` : "";
  img.alt = filme.t;
  img.loading = "lazy";
  div.appendChild(img);
  return div;
}

export function renderizarHome(fileiras) {
  const container = document.getElementById("lista-fileiras");
  container.innerHTML = "";

  for (const fileira of fileiras) {
    const secao = document.createElement("section");
    secao.className = "fileira";

    const titulo = document.createElement("a");
    titulo.href = `#/grade/${fileira.key}`;
    titulo.className = "fileira-titulo";
    titulo.textContent = fileira.title;
    secao.appendChild(titulo);

    const linha = document.createElement("div");
    linha.className = "fileira-linha";
    for (const id of fileira.ids) {
      linha.appendChild(elementoPoster(id));
    }
    secao.appendChild(linha);

    container.appendChild(secao);
  }
}
```

- [ ] **Step 2: Ligar em `app.js`**

Substitua o corpo de `aoMudarRota` em `site/js/app.js`:

```javascript
import { renderizarHome } from "./ui.js";

async function aoMudarRota(rota) {
  mostrarTela(rota.tela);

  if (rota.tela === "home") {
    const { shelves } = await carregarFileiras();
    renderizarHome(shelves);
  }
}
```

- [ ] **Step 3: Adicionar estilo das fileiras**

Acrescente a `site/style.css`:

```css
.fileira { margin-bottom: 28px; }

.fileira-titulo {
  display: block;
  color: var(--texto);
  font-weight: 600;
  text-decoration: none;
  margin-bottom: 10px;
}
.fileira-titulo:hover { color: var(--acento); }

.fileira-linha {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.poster {
  flex: 0 0 120px;
  aspect-ratio: 2 / 3;
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-elevado);
  display: block;
}
.poster img { width: 100%; height: 100%; object-fit: cover; display: block; }
```

- [ ] **Step 4: Verificar visualmente**

Sirva `site/` localmente e abra a home. Confirme via screenshot: fileiras
aparecem na ordem de `shelves.json`, cada uma com pôsteres em linha
horizontal roláve. Clique num título de fileira e confirme que a URL muda
para `#/grade/<chave>` (a tela de grade ainda está vazia — isso é esperado
até a Task 10).

- [ ] **Step 5: Commit**

```bash
git add site/js/ui.js site/js/app.js site/style.css
git commit -m "feat: tela home com as fileiras"
```

---

### Task 10: Tela Grade — filtros

A grade lida de duas formas: com uma fileira (`#/grade/<chave>`, mostra os
ids publicados daquela fileira) ou geral (`#/grade`, explora o catálogo
inteiro). Os quatro filtros (gênero, década, duração, visto) recortam em
cima da população de base — ver documento de decisões, seção sobre "ver
tudo" não significar "além do que a fileira já escolheu".

**Files:**
- Modify: `site/js/ui.js`
- Modify: `site/js/app.js`
- Modify: `site/style.css`

**Interfaces:**
- Consumes: `filtrarGrade` de `store.js`; `carregarCatalogo`,
  `carregarFileiras`; `../../data/generos.json` (novo fetch, só usado
  aqui, para rótulos do filtro de gênero); `carregarVibes`, `buscarVibe`
  de `vibes.js` (Task 8, para o campo `#busca-vibe` do cabeçalho, criado
  na Task 4 mas ainda não ligado a nada); `navegarPara` de `router.js`.
- Produces: `function renderizarGrade(filmes: Array<Filme>, titulo: string) -> void`;
  `function popularFiltroGenero(generos: Record<string,string>) -> void`.

- [ ] **Step 1: Implementar em `site/js/ui.js`**

```javascript
export function renderizarGrade(filmes, titulo) {
  document.getElementById("grade-titulo").textContent = titulo;

  const container = document.getElementById("grade-posteres");
  container.innerHTML = "";
  for (const filme of filmes) {
    const a = document.createElement("a");
    a.href = `#/filme/${filme.id}`;
    a.className = "poster";
    const img = document.createElement("img");
    img.src = filme.p ? `https://image.tmdb.org/t/p/w185${filme.p}` : "";
    img.alt = filme.t;
    img.loading = "lazy";
    a.appendChild(img);
    container.appendChild(a);
  }
}

export function popularFiltroGenero(generos) {
  const select = document.getElementById("filtro-genero");
  // Preserva a primeira opção ("Gênero", já no HTML) e adiciona o resto.
  for (const [id, nome] of Object.entries(generos).sort((a, b) => a[1].localeCompare(b[1], "pt-BR"))) {
    const opcao = document.createElement("option");
    opcao.value = id;
    opcao.textContent = nome;
    select.appendChild(opcao);
  }
}
```

- [ ] **Step 2: Ligar em `app.js`**

Substitua o corpo de `aoMudarRota` (definido na Task 6/9) pela versão
completa abaixo, e adicione o resto do bloco antes dele:

```javascript
import { renderizarHome, renderizarGrade, popularFiltroGenero } from "./ui.js";
import { filtrarGrade, obterFilme } from "./store.js";
import { carregarVibes, buscarVibe } from "./vibes.js";
import { navegarPara } from "./router.js";

let _generos = null;
let _idsVistos = new Set(); // populado de verdade na Task 14 (perfil)
let _populacaoBaseAtual = [];
let _vibeIdsAtual = null;

async function carregarGeneros() {
  if (_generos) return _generos;
  const resposta = await fetch("../data/generos.json");
  _generos = await resposta.json();
  popularFiltroGenero(_generos);
  return _generos;
}

function popularFiltroDecada(filmes) {
  const select = document.getElementById("filtro-decada");
  if (select.dataset.populado) return;
  const decadas = [...new Set(filmes.filter((f) => f.y).map((f) => Math.floor(f.y / 10) * 10))].sort((a, b) => b - a);
  for (const decada of decadas) {
    const opcao = document.createElement("option");
    opcao.value = decada;
    opcao.textContent = `${decada}s`;
    select.appendChild(opcao);
  }
  select.dataset.populado = "true";
}

function lerFiltrosAtuais() {
  return {
    genero: document.getElementById("filtro-genero").value,
    decada: document.getElementById("filtro-decada").value,
    duracao: document.getElementById("filtro-duracao").value,
    visto: document.getElementById("filtro-visto").value,
    idsVistos: _idsVistos,
    vibeIds: _vibeIdsAtual,
  };
}

async function abrirGrade(chaveFileiraOuNull, textoVibeOuNull) {
  await carregarGeneros();
  const { movies } = await carregarCatalogo();
  popularFiltroDecada(movies);

  _vibeIdsAtual = null;
  if (textoVibeOuNull) {
    const vibes = await carregarVibes();
    _vibeIdsAtual = buscarVibe(textoVibeOuNull, vibes);
  }

  if (chaveFileiraOuNull) {
    const { shelves } = await carregarFileiras();
    const fileira = shelves.find((s) => s.key === chaveFileiraOuNull);
    const idsDaFileira = new Set(fileira ? fileira.ids : []);
    _populacaoBaseAtual = movies.filter((f) => idsDaFileira.has(f.id));
    renderizarGrade(
      filtrarGrade(_populacaoBaseAtual, lerFiltrosAtuais()),
      fileira ? fileira.title : "Fileira não encontrada"
    );
  } else {
    _populacaoBaseAtual = movies;
    const titulo = textoVibeOuNull
      ? (_vibeIdsAtual ? `Vibe: ${textoVibeOuNull}` : `Nenhuma vibe encontrada para "${textoVibeOuNull}"`)
      : "Explorar tudo";
    renderizarGrade(filtrarGrade(_populacaoBaseAtual, lerFiltrosAtuais()), titulo);
  }
}

for (const idFiltro of ["filtro-genero", "filtro-decada", "filtro-duracao", "filtro-visto"]) {
  document.getElementById(idFiltro).addEventListener("change", () => {
    renderizarGrade(filtrarGrade(_populacaoBaseAtual, lerFiltrosAtuais()), document.getElementById("grade-titulo").textContent);
  });
}

document.getElementById("busca-vibe").addEventListener("keydown", (evento) => {
  if (evento.key !== "Enter") return;
  const texto = evento.target.value.trim();
  if (!texto) return;
  navegarPara(`#/grade?vibe=${encodeURIComponent(texto)}`);
});

async function aoMudarRota(rota) {
  mostrarTela(rota.tela);

  if (rota.tela === "home") {
    const { shelves } = await carregarFileiras();
    renderizarHome(shelves);
  } else if (rota.tela === "grade") {
    await abrirGrade(rota.parametro, rota.vibe ?? null);
  }
}
```

`aoMudarRota` já existia desde a Task 6 e foi reforçado na Task 9 — esta é
a versão definitiva; remova a anterior do arquivo em vez de manter as
duas.

- [ ] **Step 3: Estilo da grade**

Acrescente a `site/style.css`:

```css
.grade-cabecalho {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.grade-filtros { display: flex; gap: 8px; flex-wrap: wrap; }
.grade-filtros select {
  background: var(--bg-elevado);
  color: var(--texto);
  border: 1px solid var(--borda);
  border-radius: 6px;
  padding: 6px 8px;
}

.grade-posteres {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}
```

- [ ] **Step 4: Verificar visualmente**

Sirva `site/` localmente. Navegue `#/grade/classicos` (ou outra chave real
presente no `shelves.json` publicado) e confirme que os pôsteres daquela
fileira aparecem em grade. Mude o filtro de gênero e confirme que a lista
recorta. Navegue `#/grade` sem chave e confirme que mostra o catálogo
inteiro (pode demorar um instante a renderizar milhares de `<img>` — se
ficar visivelmente lento, isso é uma observação a registrar no relatório,
não um bloqueio desta task). Digite uma expressão de `data/vibes.json`
real (por exemplo "vingança", com acento — testa a normalização) no campo
`#busca-vibe` do cabeçalho e aperte Enter: confirme que a URL vira
`#/grade?vibe=...` e a grade mostra só filmes com aquela vibe.

- [ ] **Step 5: Commit**

```bash
git add site/js/ui.js site/js/app.js site/style.css
git commit -m "feat: tela grade com filtros de genero/decada/duracao/visto"
```

---

### Task 11: Fetch por byte-range da linha do catálogo

A ficha do filme (Task 12) precisa de pôster grande, sinopse, diretor,
elenco, keywords — dados que só existem em `catalog.jsonl`, não em
`index.json`. Usa `offsets.json` (Task 1) pra buscar só a linha do filme
via `Range`, com fallback se o servidor ignorar o header.

**Files:**
- Modify: `site/js/store.js`
- Modify: `site/js/store.test.js`

**Interfaces:**
- Consumes: `../data/offsets.json`, `../data/catalog.jsonl`.
- Produces: `async function obterDetalheFilme(id: number) -> DetalheFilme | null`
  (formato de `catalog.jsonl`: `{id,t,y,r,g,k,v,n,d,c,l,st,th,a,p,ov}`;
  `null` se o id não tiver offset publicado)

- [ ] **Step 1: Escrever os testes que falham**

Adicione a `site/js/store.test.js`:

```javascript
import { obterDetalheFilme, _resetarCacheParaTeste as resetarStore } from "./store.js";

test("obterDetalheFilme usa Range e devolve so a linha pedida", async () => {
  _resetarCacheParaTeste();
  const linhaFilme = JSON.stringify({ id: 603, t: "Matrix", ov: "sinopse" }) + "\n";

  globalThis.fetch = async (url, opcoes) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({ "603": [0, linhaFilme.length - 1] }) };
    }
    if (url.includes("catalog.jsonl")) {
      const rangeHeader = opcoes.headers.Range;
      const [, fim] = rangeHeader.match(/bytes=(\d+)-(\d+)/).slice(1).map(Number);
      return {
        ok: true, status: 206,
        text: async () => linhaFilme.slice(0, fim + 1),
      };
    }
    throw new Error(`fetch nao mockado: ${url}`);
  };

  const detalhe = await obterDetalheFilme(603);
  assert.equal(detalhe.t, "Matrix");
  assert.equal(detalhe.ov, "sinopse");
});

test("obterDetalheFilme devolve null para id sem offset", async () => {
  _resetarCacheParaTeste();
  globalThis.fetch = async (url) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    throw new Error("nao deveria buscar catalog.jsonl sem offset");
  };

  assert.equal(await obterDetalheFilme(999999), null);
});

test("obterDetalheFilme cai para o corpo inteiro quando Range nao e suportado", async () => {
  _resetarCacheParaTeste();
  const linhaFilme = JSON.stringify({ id: 1, t: "F1" }) + "\n";

  globalThis.fetch = async (url) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({ "1": [0, linhaFilme.length - 1] }) };
    }
    // Servidor ignora o Range e devolve 200 com o arquivo inteiro.
    return { ok: true, status: 200, text: async () => linhaFilme + '{"id":2,"t":"F2"}\n' };
  };

  const detalhe = await obterDetalheFilme(1);
  assert.equal(detalhe.t, "F1");
});
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/store.test.js`
Expected: FAIL — `obterDetalheFilme` não existe

- [ ] **Step 3: Implementar em `site/js/store.js`**

```javascript
// offsets.json é saída do próprio build do site (irmão de index.html em
// site/data/), por isso sem "../" -- diferente de catalog.jsonl, que vive
// na raiz do repositório. fetch() resolve caminho relativo contra a URL do
// DOCUMENTO (site/index.html), não contra a localização deste arquivo .js
// -- confirmado com new URL() antes de escrever este brief, ver documento
// de decisões do Plano 2.
const CAMINHO_OFFSETS = "data/offsets.json";
const CAMINHO_CATALOGO = "../data/catalog.jsonl";

let _offsetsCache = null;

async function carregarOffsets() {
  if (_offsetsCache) return _offsetsCache;
  const resposta = await fetch(CAMINHO_OFFSETS);
  if (!resposta.ok) {
    throw new Error(`falha ao carregar offsets.json: ${resposta.status}`);
  }
  _offsetsCache = await resposta.json();
  return _offsetsCache;
}

export async function obterDetalheFilme(id) {
  const offsets = await carregarOffsets();
  const par = offsets[String(id)];
  if (!par) return null;

  const [inicio, fim] = par;
  const resposta = await fetch(CAMINHO_CATALOGO, {
    headers: { Range: `bytes=${inicio}-${fim}` },
  });
  if (!resposta.ok) {
    throw new Error(`falha ao buscar linha do catalogo: ${resposta.status}`);
  }

  const texto = await resposta.text();

  if (resposta.status === 206) {
    // Range respeitado: o corpo JÁ é exatamente a linha pedida.
    return JSON.parse(texto.trim());
  }

  // Range ignorado (status 200, corpo inteiro ou maior que o esperado):
  // corta manualmente pelo offset conhecido.
  const trecho = texto.slice(inicio, fim + 1);
  return JSON.parse(trecho.trim());
}
```

Adicione `_offsetsCache = null;` dentro de `_resetarCacheParaTeste`.

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/store.test.js`
Expected: PASS, todos os testes do arquivo (os 5 anteriores + os 3 novos)

- [ ] **Step 5: Commit**

```bash
git add site/js/store.js site/js/store.test.js
git commit -m "feat: busca por byte-range da linha do catalogo, com fallback"
```

---

### Task 12: Tela Ficha do filme

Pôster, sinopse, ano, duração, diretor, elenco (nomes via `nomes.json`),
keywords (nomes via `nomes.json`, quando existirem), justificativa textual,
e o botão "o que mais se parece com esse" usando `motor.js`.

**Files:**
- Modify: `site/js/ui.js`
- Modify: `site/js/app.js`
- Modify: `site/style.css`

**Interfaces:**
- Consumes: `obterDetalheFilme`, `obterFilme`, `carregarCatalogo` de
  `store.js`; `filmesSimilares` de `motor.js`; `../data/nomes.json`
  (novo fetch, cacheado, usado aqui e nos títulos "Mais de"/"Com" que já
  vêm prontos em `shelves.json` — mas a ficha precisa resolver nomes de
  keyword, que não vêm em nenhum título pré-pronto).

- [ ] **Step 1: Implementar em `site/js/ui.js`**

```javascript
const URL_POSTER_GRANDE = "https://image.tmdb.org/t/p/w500";

export function renderizarFicha(detalhe, nomes) {
  const container = document.getElementById("ficha-conteudo");

  const nomeDiretores = detalhe.d.map((id) => nomes.director[id] || `#${id}`).join(", ");
  const nomeElenco = detalhe.c.map((id) => nomes.cast[id] || `#${id}`).join(", ");
  const chipsKeywords = detalhe.k
    .map((id) => nomes.keyword && nomes.keyword[id])
    .filter(Boolean);

  container.innerHTML = `
    <div class="ficha">
      <img class="ficha-poster" src="${detalhe.p ? URL_POSTER_GRANDE + detalhe.p : ""}" alt="${detalhe.t}" />
      <div class="ficha-info">
        <h2>${detalhe.t} ${detalhe.y ? `(${detalhe.y})` : ""}</h2>
        <p class="ficha-meta">${detalhe.r} min ${nomeDiretores ? "· dirigido por " + nomeDiretores : ""}</p>
        <p class="ficha-sinopse">${detalhe.ov || "Sem sinopse disponível."}</p>
        ${nomeElenco ? `<p class="ficha-elenco"><strong>Elenco:</strong> ${nomeElenco}</p>` : ""}
        ${chipsKeywords.length ? `<div class="ficha-keywords">${chipsKeywords.map((k) => `<span class="chip">${k}</span>`).join("")}</div>` : ""}
        <div class="ficha-acoes" id="ficha-acoes"></div>
        <div id="ficha-similares"></div>
      </div>
    </div>
  `;
}

export function renderizarSimilares(pares) {
  const container = document.getElementById("ficha-similares");
  if (pares.length === 0) {
    container.innerHTML = "<p>Sem sugestões parecidas no momento.</p>";
    return;
  }
  const linha = document.createElement("div");
  linha.className = "fileira-linha";
  for (const { id } of pares) {
    linha.appendChild(elementoPoster(id));
  }
  container.innerHTML = "<h3>Se você gostou desse</h3>";
  container.appendChild(linha);
}
```

- [ ] **Step 2: Ligar em `app.js`**

```javascript
import { renderizarFicha, renderizarSimilares } from "./ui.js";
import { obterDetalheFilme } from "./store.js";
import { filmesSimilares } from "./motor.js";

let _nomes = null;
async function carregarNomes() {
  if (_nomes) return _nomes;
  const resposta = await fetch("../data/nomes.json");
  _nomes = await resposta.json();
  return _nomes;
}

async function abrirFicha(id) {
  const [detalhe, nomes] = await Promise.all([obterDetalheFilme(id), carregarNomes()]);
  if (!detalhe) {
    document.getElementById("ficha-conteudo").innerHTML = "<p>Filme não encontrado.</p>";
    return;
  }
  renderizarFicha(detalhe, nomes);

  document.getElementById("ficha-similares").innerHTML = "<p>Carregando sugestões…</p>";
  const { movies } = await carregarCatalogo();
  const catalogoMapa = new Map(movies.map((f) => [f.id, f]));
  const filmeIndice = catalogoMapa.get(id);
  if (filmeIndice) {
    const configResposta = await fetch("../config.json");
    const config = await configResposta.json();
    const pares = filmesSimilares(filmeIndice, catalogoMapa, config.motor.pesos, config.motor.peso_afinidade, 12);
    renderizarSimilares(pares);
  }
}
```

E, dentro de `aoMudarRota`, adicione o ramo:

```javascript
  } else if (rota.tela === "ficha") {
    await abrirFicha(rota.parametro);
  }
```

`fetch()` resolve caminho relativo contra a URL do **documento** que carregou
o script (`site/index.html`, cuja base é `.../site/`), não contra a
localização do arquivo `.js` que fez a chamada — diferente de `import`, que
resolve contra o módulo. Por isso `"../config.json"` (um nível acima de
`site/`, onde `config.json` já vive na raiz do repositório) é o caminho
certo a partir de `site/js/app.js`, não dois níveis. Confirmado com
`new URL("../config.json", "https://.../site/").href` antes de escrever
este brief — ver documento de decisões do Plano 2.

- [ ] **Step 3: Estilo da ficha**

Acrescente a `site/style.css`:

```css
.ficha { display: flex; gap: 24px; flex-wrap: wrap; }
.ficha-poster { width: 280px; border-radius: 10px; flex-shrink: 0; }
.ficha-info { flex: 1; min-width: 260px; }
.ficha-meta { color: var(--texto-fraco); margin: 6px 0 14px; }
.ficha-sinopse { line-height: 1.5; margin-bottom: 14px; }
.ficha-keywords { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.chip {
  background: var(--bg-elevado);
  border: 1px solid var(--borda);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 0.8rem;
}
.ficha-acoes { display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0; }
```

- [ ] **Step 4: Verificar visualmente**

Sirva `site/` localmente, navegue `#/filme/<id-real-do-catalogo>` (pegue um
id existente em `data/catalog.jsonl`). Confirme via screenshot: pôster
grande, sinopse, diretor/elenco com nomes (não números cru), e uma seção
"Se você gostou desse" com pôsteres. Verifique o console do navegador sem
erro.

- [ ] **Step 5: Commit**

```bash
git add site/js/ui.js site/js/app.js site/style.css
git commit -m "feat: ficha do filme com similares via motor.js"
```

---

### Task 13: `site/js/github.js` — persistência do perfil

Token colado uma vez, guardado em `localStorage`. Leitura e escrita via
API de Conteúdo do GitHub, em lote, com merge sob conflito.

**Files:**
- Create: `site/js/github.js`
- Test: `site/js/github.test.js`

**Interfaces:**
- Consumes: `fetch` global (mockado nos testes).
- Produces:
  - `function obterToken() -> string | null` / `function salvarToken(t: string) -> void` (localStorage)
  - `async function lerPerfilRemoto(token: string) -> {perfil: object, sha: string | null}`
    (`sha: null` quando o arquivo ainda não existe — 404)
  - `function mesclarPerfis(remoto: object, local: object) -> object`
    (por filme, o registro com `at` mais recente vence; ISO date string,
    comparável lexicograficamente)
  - `async function salvarPerfilRemoto(token: string, perfil: object, sha: string | null, tentativa=1) -> {sha: string}`
    (em 409, relê, mescla, tenta de novo; até 3 tentativas; lança depois
    da terceira)

- [ ] **Step 1: Escrever os testes que falham**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  lerPerfilRemoto,
  mesclarPerfis,
  salvarPerfilRemoto,
} from "./github.js";

function base64(obj) {
  return Buffer.from(JSON.stringify(obj), "utf-8").toString("base64");
}

test("lerPerfilRemoto decodifica o conteudo e devolve o sha", async () => {
  const perfil = { movies: { "603": { seen: true, rating: 1, at: "2026-08-20" } } };
  globalThis.fetch = async () => ({
    ok: true, status: 200,
    json: async () => ({ content: base64(perfil), sha: "abc123" }),
  });

  const resultado = await lerPerfilRemoto("tok_teste");
  assert.deepEqual(resultado.perfil, perfil);
  assert.equal(resultado.sha, "abc123");
});

test("lerPerfilRemoto devolve sha nulo quando o arquivo nao existe (404)", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 404 });

  const resultado = await lerPerfilRemoto("tok_teste");
  assert.deepEqual(resultado.perfil, { movies: {} });
  assert.equal(resultado.sha, null);
});

test("mesclarPerfis mantem o registro com 'at' mais recente por filme", () => {
  const remoto = { movies: { "603": { rating: 1, at: "2026-08-20" }, "1": { rating: -1, at: "2026-08-01" } } };
  const local = { movies: { "603": { rating: -1, at: "2026-08-25" } } };

  const mesclado = mesclarPerfis(remoto, local);

  assert.equal(mesclado.movies["603"].rating, -1); // local venceu, e mais recente
  assert.equal(mesclado.movies["603"].at, "2026-08-25");
  assert.equal(mesclado.movies["1"].rating, -1); // so existia no remoto
});

test("salvarPerfilRemoto reenvia apos 409, mesclando, ate 3 tentativas", async () => {
  let chamadasPut = 0;
  globalThis.fetch = async (url, opcoes) => {
    if (opcoes.method === "GET" || !opcoes.method) {
      return { ok: true, status: 200, json: async () => ({ content: base64({ movies: {} }), sha: "sha-novo" }) };
    }
    chamadasPut++;
    if (chamadasPut === 1) {
      return { ok: false, status: 409 };
    }
    return { ok: true, status: 200, json: async () => ({ content: {}, commit: {}, content: { sha: "sha-final" } }) };
  };

  const resultado = await salvarPerfilRemoto("tok_teste", { movies: {} }, "sha-velho");
  assert.equal(chamadasPut, 2);
  assert.equal(resultado.sha, "sha-final");
});

test("salvarPerfilRemoto desiste apos 3 tentativas e lanca", async () => {
  globalThis.fetch = async (url, opcoes) => {
    if (opcoes.method === "GET" || !opcoes.method) {
      return { ok: true, status: 200, json: async () => ({ content: base64({ movies: {} }), sha: "sha-x" }) };
    }
    return { ok: false, status: 409 };
  };

  await assert.rejects(() => salvarPerfilRemoto("tok_teste", { movies: {} }, "sha-velho"));
});
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/github.test.js`
Expected: FAIL — `Cannot find module './github.js'`

- [ ] **Step 3: Implementar `site/js/github.js`**

```javascript
// Persistência do perfil via API de Conteúdo do GitHub. Projeto pessoal,
// repositório único -- owner/repo fixos de propósito, não é configurável.

const OWNER = "dicasdofabrito";
const REPO = "filmes-do-fabrito";
const CAMINHO_PERFIL = "data/profile.json";
const CHAVE_TOKEN = "fdf_token";

export function obterToken() {
  return localStorage.getItem(CHAVE_TOKEN);
}

export function salvarToken(token) {
  localStorage.setItem(CHAVE_TOKEN, token);
}

function paraBase64(texto) {
  const bytes = new TextEncoder().encode(texto);
  let binario = "";
  for (const byte of bytes) binario += String.fromCharCode(byte);
  return btoa(binario);
}

function deBase64(base64) {
  const binario = atob(base64.replace(/\n/g, ""));
  const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function cabecalhos(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

export async function lerPerfilRemoto(token) {
  const resposta = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${CAMINHO_PERFIL}`,
    { headers: cabecalhos(token) }
  );

  if (resposta.status === 404) {
    return { perfil: { movies: {} }, sha: null };
  }
  if (!resposta.ok) {
    throw new Error(`falha ao ler perfil remoto: ${resposta.status}`);
  }

  const dados = await resposta.json();
  return { perfil: JSON.parse(deBase64(dados.content)), sha: dados.sha };
}

// Por filme, o registro com `at` mais recente vence -- `at` é uma data ISO
// (YYYY-MM-DD), comparável como string.
export function mesclarPerfis(remoto, local) {
  const resultado = { movies: { ...remoto.movies } };
  for (const [id, entradaLocal] of Object.entries(local.movies || {})) {
    const entradaRemota = resultado.movies[id];
    if (!entradaRemota || (entradaLocal.at || "") >= (entradaRemota.at || "")) {
      resultado.movies[id] = entradaLocal;
    }
  }
  return resultado;
}

export async function salvarPerfilRemoto(token, perfil, sha, tentativa = 1) {
  const corpo = {
    message: "atualiza avaliacoes",
    content: paraBase64(JSON.stringify(perfil, null, 2)),
    branch: "master",
  };
  if (sha) corpo.sha = sha;

  const resposta = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${CAMINHO_PERFIL}`,
    { method: "PUT", headers: cabecalhos(token), body: JSON.stringify(corpo) }
  );

  if (resposta.ok) {
    const dados = await resposta.json();
    return { sha: dados.content.sha };
  }

  if (resposta.status === 409 && tentativa < 3) {
    const { perfil: perfilAtual, sha: shaAtual } = await lerPerfilRemoto(token);
    const mesclado = mesclarPerfis(perfilAtual, perfil);
    return salvarPerfilRemoto(token, mesclado, shaAtual, tentativa + 1);
  }

  throw new Error(`falha ao salvar perfil remoto apos ${tentativa} tentativa(s): ${resposta.status}`);
}
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/github.test.js`
Expected: PASS, 5 testes

- [ ] **Step 5: Commit**

```bash
git add site/js/github.js site/js/github.test.js
git commit -m "feat: persistencia do perfil via API de conteudo do GitHub"
```

---

### Task 14: Fila local de avaliações e botões de ação na ficha

Liga os quatro botões da ficha (já vi, gostei, não gostei, quero ver) a uma
fila local em `localStorage`, que é enviada em lote após inatividade — não
gota a gota — e drenada por `github.js`.

**Files:**
- Create: `site/js/perfil.js`
- Test: `site/js/perfil.test.js`
- Modify: `site/js/ui.js`
- Modify: `site/js/app.js`

**Interfaces:**
- Consumes: `mesclarPerfis`, `lerPerfilRemoto`, `salvarPerfilRemoto`,
  `obterToken` de `github.js`.
- Produces:
  - `function registrarAvaliacao(idFilme: number, mudanca: {seen?, rating?, want?}) -> void`
    (atualiza o perfil local em memória/localStorage, agenda o envio)
  - `function perfilLocal() -> {movies: object}`
  - `function agendarEnvio(aposMs=4000) -> void` (debounce; reagendar
    cancela o timer anterior)
  - `async function enviarPendencias() -> void` (lê token; se ausente, não
    faz nada e mantém tudo pendente; senão lê remoto, mescla local, salva,
    limpa a fila)

- [ ] **Step 1: Escrever os testes que falham**

```javascript
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import {
  registrarAvaliacao,
  perfilLocal,
  enviarPendencias,
  _resetarParaTeste,
} from "./perfil.js";
import * as github from "./github.js";

test("registrarAvaliacao atualiza o perfil local imediatamente", () => {
  _resetarParaTeste();
  registrarAvaliacao(603, { rating: 1, seen: true });

  const perfil = perfilLocal();
  assert.equal(perfil.movies["603"].rating, 1);
  assert.equal(perfil.movies["603"].seen, true);
  assert.ok(perfil.movies["603"].at); // data preenchida automaticamente
});

test("registrarAvaliacao acumula multiplas mudancas no mesmo filme", () => {
  _resetarParaTeste();
  registrarAvaliacao(1, { want: true });
  registrarAvaliacao(1, { rating: 1, seen: true });

  const entrada = perfilLocal().movies["1"];
  assert.equal(entrada.want, true);
  assert.equal(entrada.rating, 1);
});

test("enviarPendencias nao faz nada sem token", async () => {
  _resetarParaTeste();
  let chamouGithub = false;
  mock.method(github, "obterToken", () => null);
  mock.method(github, "lerPerfilRemoto", async () => { chamouGithub = true; });

  registrarAvaliacao(1, { rating: 1, seen: true });
  await enviarPendencias();

  assert.equal(chamouGithub, false);
  assert.equal(Object.keys(perfilLocal().movies).length, 1); // continua pendente
});

test("enviarPendencias mescla e envia quando ha token", async () => {
  _resetarParaTeste();
  mock.method(github, "obterToken", () => "tok_teste");
  mock.method(github, "lerPerfilRemoto", async () => ({ perfil: { movies: {} }, sha: "sha1" }));
  let enviado = null;
  mock.method(github, "salvarPerfilRemoto", async (token, perfil) => {
    enviado = perfil;
    return { sha: "sha2" };
  });

  registrarAvaliacao(603, { rating: 1, seen: true });
  await enviarPendencias();

  assert.equal(enviado.movies["603"].rating, 1);
});
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/perfil.test.js`
Expected: FAIL — `Cannot find module './perfil.js'`

- [ ] **Step 3: Implementar `site/js/perfil.js`**

```javascript
import { obterToken, lerPerfilRemoto, salvarPerfilRemoto, mesclarPerfis } from "./github.js";

const CHAVE_PERFIL_LOCAL = "fdf_perfil_local";
const INTERVALO_DEBOUNCE_MS = 4000;

let _perfil = null;
let _timerEnvio = null;

function carregarDoStorage() {
  if (_perfil) return _perfil;
  try {
    const bruto = localStorage.getItem(CHAVE_PERFIL_LOCAL);
    _perfil = bruto ? JSON.parse(bruto) : { movies: {} };
  } catch {
    _perfil = { movies: {} };
  }
  return _perfil;
}

function persistirNoStorage() {
  localStorage.setItem(CHAVE_PERFIL_LOCAL, JSON.stringify(_perfil));
}

export function perfilLocal() {
  return carregarDoStorage();
}

export function registrarAvaliacao(idFilme, mudanca) {
  const perfil = carregarDoStorage();
  const chave = String(idFilme);
  const existente = perfil.movies[chave] || {};
  perfil.movies[chave] = {
    ...existente,
    ...mudanca,
    at: new Date().toISOString().slice(0, 10),
  };
  persistirNoStorage();
  agendarEnvio();
}

export function agendarEnvio(aposMs = INTERVALO_DEBOUNCE_MS) {
  if (_timerEnvio) clearTimeout(_timerEnvio);
  _timerEnvio = setTimeout(() => {
    enviarPendencias().catch((erro) => {
      console.error("falha ao enviar avaliacoes, mantidas localmente:", erro);
    });
  }, aposMs);
}

export async function enviarPendencias() {
  const token = obterToken();
  if (!token) return; // sem token: fica tudo pendente localmente, sem erro

  const perfil = carregarDoStorage();
  if (Object.keys(perfil.movies).length === 0) return;

  const { perfil: remoto, sha } = await lerPerfilRemoto(token);
  const mesclado = mesclarPerfis(remoto, perfil);
  await salvarPerfilRemoto(token, mesclado, sha);

  _perfil = { movies: {} };
  persistirNoStorage();
}

export function _resetarParaTeste() {
  _perfil = { movies: {} };
  if (_timerEnvio) clearTimeout(_timerEnvio);
  _timerEnvio = null;
}
```

Adicione o flush ao esconder a aba, no final do arquivo (fora de qualquer
função — efeito colateral de módulo, só roda no navegador de verdade, não
durante os testes do Node, que não têm `document`):

```javascript
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      enviarPendencias().catch(() => {});
    }
  });
}
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/perfil.test.js`
Expected: PASS, 4 testes

- [ ] **Step 5: Ligar os botões na ficha**

Em `site/js/ui.js`, adicione uma função que desenha os botões e liga os
cliques (chamada de dentro de `renderizarFicha`, ao final, antes do
`return`... como a função atual não usa `return`, adicione a chamada
logo após preencher `container.innerHTML`):

```javascript
import { registrarAvaliacao, perfilLocal } from "./perfil.js";

function renderizarAcoesFicha(idFilme) {
  const container = document.getElementById("ficha-acoes");
  const entrada = perfilLocal().movies[String(idFilme)] || {};

  const botoes = [
    { rotulo: "Já vi", ativo: entrada.seen, aoClicar: () => registrarAvaliacao(idFilme, { seen: !entrada.seen }) },
    { rotulo: "👍 Gostei", ativo: entrada.rating === 1, aoClicar: () => registrarAvaliacao(idFilme, { rating: 1, seen: true }) },
    { rotulo: "👎 Não gostei", ativo: entrada.rating === -1, aoClicar: () => registrarAvaliacao(idFilme, { rating: -1, seen: true }) },
    { rotulo: "🔖 Quero ver", ativo: entrada.want, aoClicar: () => registrarAvaliacao(idFilme, { want: !entrada.want }) },
  ];

  container.innerHTML = "";
  for (const { rotulo, ativo, aoClicar } of botoes) {
    const botao = document.createElement("button");
    botao.textContent = rotulo;
    botao.className = ativo ? "botao-acao ativo" : "botao-acao";
    botao.addEventListener("click", () => {
      aoClicar();
      renderizarAcoesFicha(idFilme); // redesenha para refletir o novo estado
    });
    container.appendChild(botao);
  }
}
```

E, em `renderizarFicha`, depois de `container.innerHTML = ...`, chame:

```javascript
  renderizarAcoesFicha(detalhe.id);
```

- [ ] **Step 6: Estilo dos botões**

Acrescente a `site/style.css`:

```css
.botao-acao {
  background: var(--bg-elevado);
  color: var(--texto);
  border: 1px solid var(--borda);
  border-radius: 8px;
  padding: 8px 14px;
  cursor: pointer;
  font-size: 0.9rem;
}
.botao-acao.ativo { border-color: var(--acento); color: var(--acento); }
.botao-acao:hover { border-color: var(--acento); }
```

- [ ] **Step 7: Verificar visualmente**

Sirva `site/` localmente, abra uma ficha, clique em "👍 Gostei" e confirme
via screenshot que o botão fica destacado (classe `.ativo`). Recarregue a
página e abra a mesma ficha de novo — confirme que o estado "gostei"
persiste (leu de `localStorage`).

- [ ] **Step 8: Commit**

```bash
git add site/js/perfil.js site/js/perfil.test.js site/js/ui.js site/js/app.js site/style.css
git commit -m "feat: fila local de avaliacoes e botoes de acao na ficha"
```

---

### Task 15: Onboarding de partida a frio

Dispara quando o perfil está vazio: amostra de 200 filmes de maior
`vote_count`, diversificada por década e gênero, pra marcação rápida.

**Files:**
- Create: `site/js/onboarding.js`
- Test: `site/js/onboarding.test.js`
- Modify: `site/js/ui.js`
- Modify: `site/js/app.js`

**Interfaces:**
- Consumes: `Array<Filme>` de `index.json` (usa `n` = vote_count, `y`, `g`).
- Produces: `function amostraOnboarding(filmes: Array<Filme>, tamanho=200) -> Array<Filme>`

- [ ] **Step 1: Escrever o teste que falha**

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { amostraOnboarding } from "./onboarding.js";

function filme(id, n, y, g) {
  return { id, n, y, g: [g] };
}

test("amostraOnboarding respeita o tamanho pedido", () => {
  const filmes = Array.from({ length: 500 }, (_, i) => filme(i, 500 - i, 1980 + (i % 40), (i % 5) + 1));
  const amostra = amostraOnboarding(filmes, 50);
  assert.equal(amostra.length, 50);
});

test("amostraOnboarding prefere maior vote_count dentro de cada grupo", () => {
  const filmes = [
    filme(1, 100, 2000, 1), filme(2, 50, 2000, 1), filme(3, 200, 2010, 2),
  ];
  const amostra = amostraOnboarding(filmes, 2);
  assert.ok(amostra.some((f) => f.id === 3)); // maior vote_count geral, decada/genero diferentes
  assert.ok(amostra.some((f) => f.id === 1)); // melhor do seu grupo (decada 2000/genero 1)
});

test("amostraOnboarding nunca repete o mesmo filme", () => {
  const filmes = Array.from({ length: 20 }, (_, i) => filme(i, i, 2000, 1));
  const amostra = amostraOnboarding(filmes, 15);
  const ids = amostra.map((f) => f.id);
  assert.equal(new Set(ids).size, ids.length);
});
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `cd site && node --test js/onboarding.test.js`
Expected: FAIL — `Cannot find module './onboarding.js'`

- [ ] **Step 3: Implementar `site/js/onboarding.js`**

```javascript
// Amostra diversificada para a partida a fria: agrupa candidatos por
// (decada, primeiro genero) e escolhe em rodízio entre os grupos, sempre
// pegando o de maior vote_count restante em cada grupo -- isso espalha a
// amostra em vez de devolver vinte blockbusters americanos seguidos.

function chaveDoGrupo(filme) {
  const decada = filme.y ? Math.floor(filme.y / 10) * 10 : "sem-ano";
  const genero = filme.g[0] ?? "sem-genero";
  return `${decada}:${genero}`;
}

export function amostraOnboarding(filmes, tamanho = 200) {
  const candidatos = [...filmes].sort((a, b) => (b.n || 0) - (a.n || 0));

  const grupos = new Map();
  for (const filme of candidatos) {
    const chave = chaveDoGrupo(filme);
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(filme);
  }

  const chavesGrupos = [...grupos.keys()];
  const resultado = [];
  let indiceGrupo = 0;
  let voltasSemProgresso = 0;

  while (resultado.length < tamanho && voltasSemProgresso < chavesGrupos.length) {
    const chave = chavesGrupos[indiceGrupo % chavesGrupos.length];
    const fila = grupos.get(chave);
    if (fila && fila.length > 0) {
      resultado.push(fila.shift());
      voltasSemProgresso = 0;
    } else {
      voltasSemProgresso++;
    }
    indiceGrupo++;
  }

  return resultado;
}
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd site && node --test js/onboarding.test.js`
Expected: PASS, 3 testes

- [ ] **Step 5: Ligar na tela e no bootstrap**

Em `site/js/ui.js`:

```javascript
import { amostraOnboarding } from "./onboarding.js";

export function renderizarOnboarding(filmes, aoConcluir) {
  const amostra = amostraOnboarding(filmes, 200);
  let indice = 0;

  const container = document.getElementById("onboarding-cartoes");

  function proximo() {
    if (indice >= amostra.length) {
      aoConcluir();
      return;
    }
    const filme = amostra[indice];
    container.innerHTML = `
      <img src="https://image.tmdb.org/t/p/w342${filme.p || ""}" alt="${filme.t}" style="width:200px;border-radius:8px" />
      <p>${filme.t} ${filme.y ? `(${filme.y})` : ""}</p>
      <div class="onboarding-botoes">
        <button data-acao="visto-gostei">👍 Já vi, gostei</button>
        <button data-acao="visto-nao-gostei">👎 Já vi, não gostei</button>
        <button data-acao="nao-visto">Não vi</button>
        <button data-acao="pular">Pular</button>
      </div>
    `;
    container.querySelectorAll("button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const acao = botao.dataset.acao;
        if (acao === "visto-gostei") registrarAvaliacao(filme.id, { rating: 1, seen: true });
        else if (acao === "visto-nao-gostei") registrarAvaliacao(filme.id, { rating: -1, seen: true });
        else if (acao === "nao-visto") registrarAvaliacao(filme.id, { seen: false });
        indice++;
        proximo();
      });
    });
  }
  proximo();
}
```

Em `site/js/app.js`, na função `iniciar`, decida se mostra onboarding em
vez da home quando o perfil estiver vazio:

```javascript
import { renderizarOnboarding } from "./ui.js";
import { perfilLocal } from "./perfil.js";

async function iniciar() {
  const { movies } = await carregarCatalogo();
  await carregarFileiras();

  const perfilVazio = Object.keys(perfilLocal().movies).length === 0;
  if (perfilVazio && !localStorage.getItem("fdf_onboarding_visto")) {
    document.getElementById("onboarding").classList.remove("oculto");
    renderizarOnboarding(movies, () => {
      localStorage.setItem("fdf_onboarding_visto", "true");
      document.getElementById("onboarding").classList.add("oculto");
      iniciarRoteador(aoMudarRota);
    });
    return;
  }

  iniciarRoteador(aoMudarRota);
}
```

- [ ] **Step 6: Estilo do onboarding**

```css
#onboarding { text-align: center; padding-top: 40px; }
.onboarding-botoes { display: flex; gap: 8px; justify-content: center; margin-top: 16px; flex-wrap: wrap; }
```

- [ ] **Step 7: Verificar visualmente**

Limpe o `localStorage` do navegador de teste (ou use uma aba anônima),
sirva `site/` e abra a página — confirme via screenshot que o onboarding
aparece antes da home, mostra um pôster por vez, e os botões avançam pro
próximo filme.

- [ ] **Step 8: Commit**

```bash
git add site/js/onboarding.js site/js/onboarding.test.js site/js/ui.js site/js/app.js site/style.css
git commit -m "feat: onboarding de partida a fria"
```

---

### Task 16: Automação — `.github/workflows/sync.yml`

O cron diário que roda o pipeline sozinho. Como Pages está configurado pra
servir a raiz de `master` (Task de hospedagem, feita manualmente pelo
Fabio), todo push deste workflow já republica o site — nenhum passo de
deploy adicional é necessário.

**Files:**
- Create: `.github/workflows/sync.yml`

**Interfaces:**
- Consumes: segredo `TMDB_TOKEN` já cadastrado no repositório (pendência 1
  do spec original, resolvida antes da carga inicial do Plano 1).
- Produces: nada que outro código consuma — é o job agendado.

- [ ] **Step 1: Escrever o workflow**

```yaml
name: Sync diário

on:
  schedule:
    - cron: "0 9 * * *"  # 09:00 UTC = 06:00 BRT
  workflow_dispatch: {}

permissions:
  contents: write
  issues: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Instala dependências
        run: pip install -e ".[dev]"

      - name: Roda o sync
        env:
          TMDB_TOKEN: ${{ secrets.TMDB_TOKEN }}
        run: python -m sync

      - name: Commit e push se algo mudou
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ site/data/
          git diff --staged --quiet || git commit -m "chore: sync diário do catálogo"
          git push

      - name: Abre issue se o sync falhou
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `Sync diário falhou em ${new Date().toISOString().slice(0, 10)}`,
              body: `O workflow de sync falhou. Ver o run: ${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
              labels: ["sync-falhou"],
            });
```

- [ ] **Step 2: Validar a sintaxe do YAML**

Run: `.venv/Scripts/python -c "import yaml; yaml.safe_load(open('.github/workflows/sync.yml', encoding='utf-8')); print('YAML valido')"`
Expected: imprime `YAML valido`. Se `yaml` não estiver instalado no
ambiente, `pip install pyyaml` antes (só para essa checagem local, não
precisa entrar em `pyproject.toml` — não é dependência do projeto).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/sync.yml
git commit -m "feat: automatiza o sync diario via GitHub Actions"
```

---

## Cobertura do spec

| Seção do spec | Onde é implementada |
|---|---|
| 4.4 index vs. catalog (split) | Task 1 (extensão de campos) — já implementado na spec original |
| 6.4 "gostei de X, o que mais?" (versão ficha) | Task 7 (motor.js), Task 12 |
| 7.1 as onze fileiras na home | Task 9 (consome `shelves.json`, já pronto do Plano 1) |
| 7.2 grade com filtros | Task 10 |
| 7.3 ficha do filme | Task 12, Task 14 (ações) |
| 7.4 busca por vibe | Task 8 (lógica), Task 10 (campo do cabeçalho ligado à navegação) |
| 8 persistência do perfil (token, lote, conflito) | Task 13, Task 14 |
| 9 falha silenciosa do Actions → issue | Task 16 |
| 12 atribuição do TMDB | Task 4 |
| 6.3 onboarding de partida a fria | Task 15 |
| 3 arquitetura (Pages servindo o site) | decisão de design #1 — passo manual do Fabio |
| 5 (step 9, commit/push do sync) | Task 16 |

## Ordem de construção

Tasks 1–3 (extensões do pipeline) não dependem de nada do site e podem, em
princípio, rodar em paralelo entre si — mas como são poucas e pequenas,
sequenciais é mais simples de revisar. Tasks 4–6 formam a base do site.
Tasks 7–8 são módulos de lógica pura, independentes um do outro e das
telas — podem ser feitas em qualquer ordem relativa entre si, mas antes das
tasks que os consomem (9–15). A partir da Task 9, a ordem segue a
dependência natural: home → grade → fetch de detalhe → ficha → persistência
→ onboarding → automação.

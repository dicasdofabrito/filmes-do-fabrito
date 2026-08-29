// Camada de acesso a dados: busca index.json/shelves.json uma vez, cacheia
// em memória, e expõe consultas. Nenhum outro módulo faz fetch desses dois
// arquivos diretamente -- é este módulo, e só ele, que sabe o caminho.

// index.json e shelves.json sao saida do proprio build do site, irmaos de
// index.html em site/data/ -- por isso sem "../". fetch() resolve caminho
// relativo contra a URL do documento (site/index.html), nao contra a
// localizacao deste arquivo .js.
const CAMINHO_INDICE = "data/index.json";
const CAMINHO_FILEIRAS = "data/shelves.json";

// offsets.json é saída do próprio build do site (irmão de index.html em
// site/data/), por isso sem "../" -- diferente de catalog.jsonl, que vive
// na raiz do repositório. fetch() resolve caminho relativo contra a URL do
// DOCUMENTO (site/index.html), não contra a localização deste arquivo .js
// -- confirmado com new URL() antes de escrever este brief, ver documento
// de decisões do Plano 2.
const CAMINHO_OFFSETS = "data/offsets.json";
const CAMINHO_CATALOGO = "../data/catalog.jsonl";

let _catalogoPromise = null;
let _fileirasPromise = null;
let _porId = null;
let _offsetsCache = null;

export async function carregarCatalogo() {
  if (!_catalogoPromise) {
    _catalogoPromise = fetch(CAMINHO_INDICE).then(async (resposta) => {
      if (!resposta.ok) {
        throw new Error(`falha ao carregar index.json: ${resposta.status}`);
      }
      const dados = await resposta.json();
      _porId = new Map(dados.movies.map((f) => [f.id, f]));
      return dados;
    });
  }
  return _catalogoPromise;
}

export async function carregarFileiras() {
  if (!_fileirasPromise) {
    _fileirasPromise = fetch(CAMINHO_FILEIRAS).then(async (resposta) => {
      if (!resposta.ok) {
        throw new Error(`falha ao carregar shelves.json: ${resposta.status}`);
      }
      return resposta.json();
    });
  }
  return _fileirasPromise;
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

  if (resposta.status === 206) {
    // Range respeitado: o corpo JÁ é exatamente a linha pedida.
    const texto = await resposta.text();
    return JSON.parse(texto.trim());
  }

  // Range ignorado (status 200, corpo inteiro ou maior que o esperado):
  // precisamos cortar pelo offset em BYTES, e só decodificar DEPOIS.
  // inicio/fim vêm de offsets.json em bytes UTF-8 (Task 1). Se a gente
  // chamasse resposta.text() primeiro, o corpo já viraria uma string JS
  // (UTF-16) e .slice() passaria a contar unidades de caractere, não byte
  // -- qualquer caractere multi-byte (acento, etc.) antes ou dentro da
  // linha pedida desalinharia o corte. Por isso lemos como arrayBuffer(),
  // cortamos o Uint8Array cru e só então decodificamos.
  const buffer = await resposta.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const trecho = bytes.slice(inicio, fim + 1);
  const texto = new TextDecoder("utf-8").decode(trecho);
  return JSON.parse(texto.trim());
}

export function _resetarCacheParaTeste() {
  _catalogoPromise = null;
  _fileirasPromise = null;
  _porId = null;
  _offsetsCache = null;
}

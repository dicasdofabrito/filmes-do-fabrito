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

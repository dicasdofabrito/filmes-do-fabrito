import { iniciarRoteador, navegarPara } from "./router.js";
import { carregarCatalogo, carregarFileiras, filtrarGrade, obterFilme, obterDetalheFilme } from "./store.js";
import { renderizarHome, renderizarGrade, popularFiltroGenero, renderizarFicha, renderizarSimilares, renderizarOnboarding } from "./ui.js";
import { carregarVibes, buscarVibe } from "./vibes.js";
import { filmesSimilares } from "./motor.js";
import { perfilLocal } from "./perfil.js";

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

let _generos = null;
let _idsVistos = new Set(); // repopulado a cada abrirGrade() a partir de perfilLocal() (Task 14)
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

// Filtros de população base por um id único (keyword/diretor/ator clicado
// na ficha) -- cada um casa contra o array correspondente do índice
// (k/d/c, já publicados desde o Plano 2). Chave é o nome do parâmetro que
// router.js extrai da query string; campo é a propriedade do Filme;
// balde é o balde correspondente em nomes.json; rotulo monta o título.
const FILTROS_POR_PESSOA_OU_KEYWORD = [
  { chave: "keyword", campo: "k", balde: "keyword", rotulo: (nome) => `Filmes com a keyword: ${nome}` },
  { chave: "diretor", campo: "d", balde: "director", rotulo: (nome) => `Filmes com ${nome}` },
  { chave: "ator", campo: "c", balde: "cast", rotulo: (nome) => `Filmes com ${nome}` },
];

async function abrirGrade(rota) {
  _idsVistos = new Set(
    Object.entries(perfilLocal().movies)
      .filter(([, entrada]) => entrada.seen)
      .map(([id]) => Number(id))
  );
  await carregarGeneros();
  const { movies } = await carregarCatalogo();
  popularFiltroDecada(movies);

  _vibeIdsAtual = null;
  if (rota.vibe) {
    const vibes = await carregarVibes();
    _vibeIdsAtual = buscarVibe(rota.vibe, vibes);
  }

  const porPessoaOuKeyword = FILTROS_POR_PESSOA_OU_KEYWORD.find((f) => rota[f.chave] != null);

  if (porPessoaOuKeyword) {
    const id = rota[porPessoaOuKeyword.chave];
    const nomes = await carregarNomes();
    _populacaoBaseAtual = movies.filter((f) => (f[porPessoaOuKeyword.campo] || []).includes(id));
    const nome = (nomes[porPessoaOuKeyword.balde] && nomes[porPessoaOuKeyword.balde][id]) || `#${id}`;
    renderizarGrade(filtrarGrade(_populacaoBaseAtual, lerFiltrosAtuais()), porPessoaOuKeyword.rotulo(nome));
  } else if (rota.parametro) {
    const { shelves } = await carregarFileiras();
    const fileira = shelves.find((s) => s.key === rota.parametro);
    const idsDaFileira = new Set(fileira ? fileira.ids : []);
    _populacaoBaseAtual = movies.filter((f) => idsDaFileira.has(f.id));
    renderizarGrade(
      filtrarGrade(_populacaoBaseAtual, lerFiltrosAtuais()),
      fileira ? fileira.title : "Fileira não encontrada"
    );
  } else {
    _populacaoBaseAtual = movies;
    const titulo = rota.vibe
      ? (_vibeIdsAtual ? `Vibe: ${rota.vibe}` : `Nenhuma vibe encontrada para "${rota.vibe}"`)
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

async function aoMudarRota(rota) {
  mostrarTela(rota.tela);

  if (rota.tela === "home") {
    const { shelves } = await carregarFileiras();
    renderizarHome(shelves);
  } else if (rota.tela === "grade") {
    await abrirGrade(rota);
  } else if (rota.tela === "ficha") {
    await abrirFicha(rota.parametro);
  }
}

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

iniciar();

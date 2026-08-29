import { iniciarRoteador, navegarPara } from "./router.js";
import { carregarCatalogo, carregarFileiras, filtrarGrade, obterFilme } from "./store.js";
import { renderizarHome, renderizarGrade, popularFiltroGenero } from "./ui.js";
import { carregarVibes, buscarVibe } from "./vibes.js";

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

async function iniciar() {
  await Promise.all([carregarCatalogo(), carregarFileiras()]);
  iniciarRoteador(aoMudarRota);
}

iniciar();

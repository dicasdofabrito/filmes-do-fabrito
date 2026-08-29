import { iniciarRoteador } from "./router.js";
import { carregarCatalogo, carregarFileiras } from "./store.js";
import { renderizarHome } from "./ui.js";

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

  if (rota.tela === "home") {
    const { shelves } = await carregarFileiras();
    renderizarHome(shelves);
  }
  // grade/ficha são preenchidas nas próximas tasks.
}

async function iniciar() {
  await Promise.all([carregarCatalogo(), carregarFileiras()]);
  iniciarRoteador(aoMudarRota);
}

iniciar();

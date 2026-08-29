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

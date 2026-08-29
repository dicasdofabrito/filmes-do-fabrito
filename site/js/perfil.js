// Fila local de avaliações: registra ações do usuário (já vi / avaliou /
// quero ver) em localStorage e envia em lote ao GitHub após inatividade,
// via github.js.

import * as github from "./github.js";

// Indireção mutável sobre github.js: propriedades de um objeto namespace de
// módulo ES são não-configuráveis por especificação, então `mock.method`
// nunca consegue substituir `github.obterToken` diretamente em nenhuma
// versão do Node (não é peculiaridade de versão). Por isso perfil.js chama
// tudo através deste objeto comum -- que é um objeto plano de verdade, com
// propriedades configuráveis -- e os testes mockam nele em vez de mockar o
// namespace do módulo importado.
export const _dependenciasGithub = {
  obterToken: github.obterToken,
  lerPerfilRemoto: github.lerPerfilRemoto,
  salvarPerfilRemoto: github.salvarPerfilRemoto,
  mesclarPerfis: github.mesclarPerfis,
};

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
  const token = _dependenciasGithub.obterToken();
  if (!token) return; // sem token: fica tudo pendente localmente, sem erro

  const perfil = carregarDoStorage();
  if (Object.keys(perfil.movies).length === 0) return;

  const { perfil: remoto, sha } = await _dependenciasGithub.lerPerfilRemoto(token);
  const mesclado = _dependenciasGithub.mesclarPerfis(remoto, perfil);
  await _dependenciasGithub.salvarPerfilRemoto(token, mesclado, sha);

  _perfil = { movies: {} };
  persistirNoStorage();
}

export function _resetarParaTeste() {
  _perfil = { movies: {} };
  if (_timerEnvio) clearTimeout(_timerEnvio);
  _timerEnvio = null;
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      enviarPendencias().catch(() => {});
    }
  });
}

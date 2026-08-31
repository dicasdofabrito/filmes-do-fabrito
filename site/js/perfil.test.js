import { test, mock } from "node:test";
import assert from "node:assert/strict";

// Ruling: Node (testado em v24.20.0) não expõe `localStorage` global por
// padrão -- exige `--localstorage-file` ou `--experimental-webstorage`. O
// brief previu esse risco e autorizou um polyfill mínimo no arquivo de
// teste como saída; é isso que fazemos aqui, condicionado para não pisar
// em uma implementação nativa caso uma versão futura do Node já a exponha.
if (typeof globalThis.localStorage === "undefined") {
  const _armazenamento = new Map();
  globalThis.localStorage = {
    getItem: (chave) => (_armazenamento.has(chave) ? _armazenamento.get(chave) : null),
    setItem: (chave, valor) => _armazenamento.set(chave, String(valor)),
    removeItem: (chave) => _armazenamento.delete(chave),
    clear: () => _armazenamento.clear(),
  };
}

import {
  registrarAvaliacao,
  perfilLocal,
  enviarPendencias,
  sincronizarNaAbertura,
  _resetarParaTeste,
  _dependenciasGithub as github,
} from "./perfil.js";

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

test("sincronizarNaAbertura nao faz nada sem token", async () => {
  _resetarParaTeste();
  let chamouGithub = false;
  mock.method(github, "obterToken", () => null);
  mock.method(github, "lerPerfilRemoto", async () => { chamouGithub = true; });

  await sincronizarNaAbertura();

  assert.equal(chamouGithub, false);
});

test("sincronizarNaAbertura puxa o perfil remoto e popula o local vazio", async () => {
  _resetarParaTeste();
  mock.method(github, "obterToken", () => "tok_teste");
  mock.method(github, "lerPerfilRemoto", async () => ({
    perfil: { movies: { "603": { seen: true, rating: 1, at: "2026-08-20" } } },
    sha: "sha1",
  }));

  await sincronizarNaAbertura();

  assert.equal(perfilLocal().movies["603"].rating, 1);
});

test("sincronizarNaAbertura mescla com o local em vez de sobrescrever", async () => {
  _resetarParaTeste();
  registrarAvaliacao(1, { want: true }); // so existe local
  mock.method(github, "obterToken", () => "tok_teste");
  mock.method(github, "lerPerfilRemoto", async () => ({
    perfil: { movies: { "603": { seen: true, rating: 1, at: "2026-08-20" } } },
    sha: "sha1",
  }));

  await sincronizarNaAbertura();

  const perfil = perfilLocal();
  assert.equal(perfil.movies["1"].want, true); // preservado
  assert.equal(perfil.movies["603"].rating, 1); // puxado do remoto
});

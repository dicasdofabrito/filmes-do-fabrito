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

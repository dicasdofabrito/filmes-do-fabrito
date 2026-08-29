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

test("grade com query de keyword", () => {
  assert.deepEqual(analisarHash("#/grade?keyword=16"), {
    tela: "grade", parametro: null, keyword: 16,
  });
});

test("grade com query de diretor", () => {
  assert.deepEqual(analisarHash("#/grade?diretor=77"), {
    tela: "grade", parametro: null, diretor: 77,
  });
});

test("grade com query de ator", () => {
  assert.deepEqual(analisarHash("#/grade?ator=88"), {
    tela: "grade", parametro: null, ator: 88,
  });
});

test("query de keyword/diretor/ator nao numerica e ignorada", () => {
  const rota = analisarHash("#/grade?keyword=abc");
  assert.equal("keyword" in rota, false);
});

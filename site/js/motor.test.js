import { test } from "node:test";
import assert from "node:assert/strict";
import {
  featuresDe,
  construirGostoDeUmFilme,
  afinidade,
  filmesSimilares,
} from "./motor.js";

const PESOS = { keyword: 0.4, director: 0.2, cast: 0.15, genre: 0.15, decade: 0.06, language: 0.04 };

function filme(id, extra = {}) {
  return { id, y: 2000, g: [], k: [], d: [], c: [], l: "en", ...extra };
}

test("featuresDe deriva a decada do ano", () => {
  assert.deepEqual(featuresDe(filme(1, { y: 1999 })).decade, [1990]);
  assert.deepEqual(featuresDe(filme(2, { y: null })).decade, []);
});

test("caracteristica rara pesa mais que a comum", () => {
  // 'comum' esta em todos os 10 filmes do catalogo; 'rara' so no filme 1.
  const catalogo = new Map();
  for (let i = 1; i <= 10; i++) catalogo.set(i, filme(i, { k: [100] }));
  catalogo.set(1, filme(1, { k: [100, 200] }));

  const gosto = construirGostoDeUmFilme(catalogo.get(1), catalogo, PESOS);

  assert.ok(gosto.get("keyword:200") > gosto.get("keyword:100"));
});

test("afinidade e 1.0 quando todas as caracteristicas do filme batem com o gosto", () => {
  const gosto = new Map([["genre:18", 1.0]]);
  assert.equal(afinidade(filme(1, { g: [18] }), gosto, PESOS), 1.0);
});

test("afinidade e 0 quando nenhuma caracteristica e conhecida", () => {
  const gosto = new Map([["genre:99", 1.0]]);
  assert.equal(afinidade(filme(1, { g: [18] }), gosto, PESOS), 0);
});

test("filmesSimilares exclui o proprio filme de referencia e ordena por score", () => {
  const catalogo = new Map();
  for (let i = 1; i <= 5; i++) catalogo.set(i, filme(i, { g: [18] }));
  catalogo.set(3, filme(3, { g: [99] })); // o menos parecido

  const referencia = catalogo.get(1);
  const resultado = filmesSimilares(referencia, catalogo, PESOS, 0.75, 10);

  assert.ok(!resultado.some((r) => r.id === 1));
  assert.ok(resultado.length > 0);
  for (let i = 1; i < resultado.length; i++) {
    assert.ok(resultado[i - 1].score >= resultado[i].score);
  }
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { amostraOnboarding } from "./onboarding.js";

function filme(id, n, y, g) {
  return { id, n, y, g: [g] };
}

test("amostraOnboarding respeita o tamanho pedido", () => {
  const filmes = Array.from({ length: 500 }, (_, i) => filme(i, 500 - i, 1980 + (i % 40), (i % 5) + 1));
  const amostra = amostraOnboarding(filmes, 50);
  assert.equal(amostra.length, 50);
});

test("amostraOnboarding prefere maior vote_count dentro de cada grupo", () => {
  const filmes = [
    filme(1, 100, 2000, 1), filme(2, 50, 2000, 1), filme(3, 200, 2010, 2),
  ];
  const amostra = amostraOnboarding(filmes, 2);
  assert.ok(amostra.some((f) => f.id === 3)); // maior vote_count geral, decada/genero diferentes
  assert.ok(amostra.some((f) => f.id === 1)); // melhor do seu grupo (decada 2000/genero 1)
});

test("amostraOnboarding nunca repete o mesmo filme", () => {
  const filmes = Array.from({ length: 20 }, (_, i) => filme(i, i, 2000, 1));
  const amostra = amostraOnboarding(filmes, 15);
  const ids = amostra.map((f) => f.id);
  assert.equal(new Set(ids).size, ids.length);
});

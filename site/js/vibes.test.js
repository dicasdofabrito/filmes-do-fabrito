import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizarTexto, buscarVibe } from "./vibes.js";

test("normalizarTexto remove acento e caixa", () => {
  assert.equal(normalizarTexto("Vingança"), "vinganca");
  assert.equal(normalizarTexto("  Fim do Mundo  "), "fim do mundo");
  assert.equal(normalizarTexto("esperança"), "esperanca");
});

test("buscarVibe encontra com ou sem acento na consulta", () => {
  const vibes = new Map([["vinganca", [900, 901]]]);
  assert.deepEqual(buscarVibe("vingança", vibes), [900, 901]);
  assert.deepEqual(buscarVibe("VINGANCA", vibes), [900, 901]);
  assert.equal(buscarVibe("algo que nao existe", vibes), null);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  carregarCatalogo,
  obterFilme,
  filtrarGrade,
  obterDetalheFilme,
  _resetarCacheParaTeste,
} from "./store.js";

function mockFetch(respostas) {
  globalThis.fetch = async (url) => {
    const chave = Object.keys(respostas).find((k) => url.includes(k));
    if (!chave) throw new Error(`fetch nao mockado para ${url}`);
    return {
      ok: true,
      status: 200,
      json: async () => respostas[chave],
    };
  };
}

test("carregarCatalogo busca uma vez e cacheia", async () => {
  _resetarCacheParaTeste();
  let chamadas = 0;
  globalThis.fetch = async () => {
    chamadas++;
    return { ok: true, status: 200, json: async () => ({ movies: [{ id: 1, t: "F1" }] }) };
  };

  await carregarCatalogo();
  await carregarCatalogo();

  assert.equal(chamadas, 1);
});

test("carregarCatalogo chamado duas vezes em paralelo busca uma unica vez", async () => {
  _resetarCacheParaTeste();
  let chamadas = 0;
  globalThis.fetch = async () => {
    chamadas++;
    return { ok: true, status: 200, json: async () => ({ movies: [{ id: 1, t: "F1" }] }) };
  };

  const [a, b] = await Promise.all([carregarCatalogo(), carregarCatalogo()]);

  assert.equal(chamadas, 1);
  assert.deepEqual(a, b);
});

test("obterFilme encontra pelo id apos carregar", async () => {
  _resetarCacheParaTeste();
  mockFetch({ "index.json": { movies: [{ id: 603, t: "Matrix", y: 1999 }] } });

  await carregarCatalogo();

  assert.deepEqual(obterFilme(603), { id: 603, t: "Matrix", y: 1999 });
  assert.equal(obterFilme(999), undefined);
});

test("filtrarGrade combina genero, decada, duracao e visto", () => {
  const filmes = [
    { id: 1, y: 1999, r: 90, g: [28] },
    { id: 2, y: 1999, r: 150, g: [18] },
    { id: 3, y: 2020, r: 90, g: [28] },
  ];

  const soAcao90s = filtrarGrade(filmes, {
    genero: 28, decada: 1990, duracao: "", visto: "", idsVistos: new Set(),
  });
  assert.deepEqual(soAcao90s.map((f) => f.id), [1]);

  const soCurto = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "curto", visto: "", idsVistos: new Set(),
  });
  assert.deepEqual(soCurto.map((f) => f.id).sort(), [1, 3]);

  const soNaoVistos = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "", visto: "nao-visto", idsVistos: new Set([1]),
  });
  assert.deepEqual(soNaoVistos.map((f) => f.id).sort(), [2, 3]);
});

test("filtrarGrade sem nenhum filtro devolve tudo", () => {
  const filmes = [{ id: 1, y: 2000, r: 100, g: [1] }];
  const resultado = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "", visto: "", idsVistos: new Set(),
  });
  assert.equal(resultado.length, 1);
});

test("filtrarGrade com vibeIds exige interseccao de keywords", () => {
  const filmes = [
    { id: 1, y: 2000, r: 100, g: [1], k: [900] },
    { id: 2, y: 2000, r: 100, g: [1], k: [901] },
    { id: 3, y: 2000, r: 100, g: [1], k: [] },
  ];
  const resultado = filtrarGrade(filmes, {
    genero: "", decada: "", duracao: "", visto: "", idsVistos: new Set(),
    vibeIds: [900, 950],
  });
  assert.deepEqual(resultado.map((f) => f.id), [1]);
});

test("obterDetalheFilme usa Range e devolve so a linha pedida", async () => {
  _resetarCacheParaTeste();
  const linhaFilme = JSON.stringify({ id: 603, t: "Matrix", ov: "sinopse" }) + "\n";

  globalThis.fetch = async (url, opcoes) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({ "603": [0, linhaFilme.length - 1] }) };
    }
    if (url.includes("catalog.jsonl")) {
      const rangeHeader = opcoes.headers.Range;
      const [, fim] = rangeHeader.match(/bytes=(\d+)-(\d+)/).slice(1).map(Number);
      return {
        ok: true, status: 206,
        text: async () => linhaFilme.slice(0, fim + 1),
      };
    }
    throw new Error(`fetch nao mockado: ${url}`);
  };

  const detalhe = await obterDetalheFilme(603);
  assert.equal(detalhe.t, "Matrix");
  assert.equal(detalhe.ov, "sinopse");
});

test("obterDetalheFilme devolve null para id sem offset", async () => {
  _resetarCacheParaTeste();
  globalThis.fetch = async (url) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    throw new Error("nao deveria buscar catalog.jsonl sem offset");
  };

  assert.equal(await obterDetalheFilme(999999), null);
});

test("obterDetalheFilme cai para o corpo inteiro quando Range nao e suportado", async () => {
  _resetarCacheParaTeste();
  const linhaFilme = JSON.stringify({ id: 1, t: "F1" }) + "\n";
  const arquivo = linhaFilme + '{"id":2,"t":"F2"}\n';
  const inicioBytes = 0;
  const fimBytes = Buffer.byteLength(linhaFilme, "utf8") - 1;

  globalThis.fetch = async (url) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({ "1": [inicioBytes, fimBytes] }) };
    }
    // Servidor ignora o Range e devolve 200 com o arquivo inteiro (bytes crus).
    return {
      ok: true, status: 200,
      arrayBuffer: async () => new TextEncoder().encode(arquivo).buffer,
    };
  };

  const detalhe = await obterDetalheFilme(1);
  assert.equal(detalhe.t, "F1");
});

test("obterDetalheFilme corta pelo offset em BYTES no fallback (acento antes da linha nao desalinha o corte)", async () => {
  _resetarCacheParaTeste();
  // "Amélie" tem um caractere multi-byte ("é" = 2 bytes UTF-8, mas 1 unidade
  // UTF-16/char). Isso faz o offset em bytes do começo de linhaFilme ficar
  // 1 posição à frente do offset em caracteres -- exatamente o cenário que
  // quebrava o parse de "Ariel" (dir: "Aki Kaurismäki") em producao.
  const linhaAnterior = JSON.stringify({ id: 1, t: "Amélie", dir: "Jean-Pierre Jeunet" }) + "\n";
  const linhaFilme = JSON.stringify({ id: 2, t: "Ariel", dir: "Aki Kaurismäki" }) + "\n";
  const arquivo = linhaAnterior + linhaFilme;

  const inicioBytes = Buffer.byteLength(linhaAnterior, "utf8");
  const fimBytes = inicioBytes + Buffer.byteLength(linhaFilme, "utf8") - 1;

  globalThis.fetch = async (url) => {
    if (url.includes("offsets.json")) {
      return { ok: true, status: 200, json: async () => ({ "2": [inicioBytes, fimBytes] }) };
    }
    // Servidor ignora o Range e devolve 200 com o arquivo inteiro (bytes crus,
    // nao string ja decodificada -- o bug so aparece se cortarmos bytes reais).
    return {
      ok: true, status: 200,
      arrayBuffer: async () => new TextEncoder().encode(arquivo).buffer,
    };
  };

  const detalhe = await obterDetalheFilme(2);
  assert.equal(detalhe.t, "Ariel");
  assert.equal(detalhe.dir, "Aki Kaurismäki");
});

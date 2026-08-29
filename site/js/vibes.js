// vibes.json tem chaves sem acento (herdado da primeira versão do
// dicionário). Normalizar dos dois lados -- a chave armazenada e a
// consulta digitada -- faz o casamento funcionar hoje e continuar
// funcionando se as chaves forem re-acentuadas no futuro.

const CAMINHO_VIBES = "../data/vibes.json";

let _vibesCache = null;

export function normalizarTexto(texto) {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export async function carregarVibes() {
  if (_vibesCache) return _vibesCache;

  const resposta = await fetch(CAMINHO_VIBES);
  if (!resposta.ok) {
    throw new Error(`falha ao carregar vibes.json: ${resposta.status}`);
  }
  const bruto = await resposta.json();

  _vibesCache = new Map(
    Object.entries(bruto).map(([chave, ids]) => [normalizarTexto(chave), ids])
  );
  return _vibesCache;
}

export function buscarVibe(consulta, vibesCarregadas) {
  const chave = normalizarTexto(consulta);
  return vibesCarregadas.get(chave) ?? null;
}

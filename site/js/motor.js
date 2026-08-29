// Porta fiel de sync/score.py + sync/profile.py, para a ficha do filme
// poder calcular "o que mais se parece com esse" sem servidor -- ver
// documento de decisões do Plano 2, seção 7. Mesma fórmula, mesmos pesos.

function decadaDe(filme) {
  return filme.y ? Math.floor(filme.y / 10) * 10 : null;
}

export function featuresDe(filme) {
  return {
    keyword: filme.k || [],
    director: filme.d || [],
    cast: filme.c || [],
    genre: filme.g || [],
    decade: filme.y ? [decadaDe(filme)] : [],
    language: filme.l ? [filme.l] : [],
  };
}

function frequenciaNoCatalogo(catalogo) {
  const freq = new Map();
  for (const filme of catalogo.values()) {
    const features = featuresDe(filme);
    for (const [tipo, valores] of Object.entries(features)) {
      for (const valor of new Set(valores)) {
        const chave = `${tipo}:${valor}`;
        freq.set(chave, (freq.get(chave) || 0) + 1);
      }
    }
  }
  return freq;
}

// Constrói o vetor de gosto a partir de UM filme (positivo) contra o
// catálogo inteiro -- mesma suavização e mesmo idf que o pipeline usa em
// gosto_de_um_filme / construir_gosto (sync/profile.py).
export function construirGostoDeUmFilme(filmeReferencia, catalogo, pesos, k = 2.0) {
  const freq = frequenciaNoCatalogo(catalogo);
  const total = Math.max(catalogo.size, 1);
  const gosto = new Map();

  const features = featuresDe(filmeReferencia);
  for (const [tipo, valores] of Object.entries(features)) {
    for (const valor of new Set(valores)) {
      const chave = `${tipo}:${valor}`;
      const p = 1;
      const n = 0;
      const afin = (p - n) / (p + n + k);
      const idf = Math.log(total / (1 + (freq.get(chave) || 0)));
      gosto.set(chave, afin * idf);
    }
  }
  return gosto;
}

export function afinidade(filme, gosto, pesos) {
  const features = featuresDe(filme);
  const presentes = {};

  for (const [tipo, valores] of Object.entries(features)) {
    const unicos = new Set(valores);
    if (unicos.size === 0) continue;
    let soma = 0;
    for (const valor of unicos) soma += gosto.get(`${tipo}:${valor}`) || 0;
    presentes[tipo] = soma / unicos.size;
  }

  const tipos = Object.keys(presentes);
  if (tipos.length === 0) return 0;

  const totalPeso = tipos.reduce((acc, t) => acc + (pesos[t] || 0), 0);
  if (totalPeso === 0) return 0;

  return tipos.reduce(
    (acc, t) => acc + (pesos[t] / totalPeso) * presentes[t], 0
  );
}

// Sem uma âncora de qualidade separada disponível no cliente (index.json
// só publica o score final já misturado, não afinidade/qualidade
// separadas), usamos só a afinidade normalizada entre os candidatos como
// critério de ordenação -- diferente da fileira "similar" do próprio
// pipeline, que tem acesso à qualidade bayesiana calculada no servidor.
export function filmesSimilares(filmeReferencia, catalogo, pesos, pesoAfinidade, limite = 24) {
  const gosto = construirGostoDeUmFilme(filmeReferencia, catalogo, pesos);
  const candidatos = [...catalogo.values()].filter((f) => f.id !== filmeReferencia.id);

  const pontuados = candidatos.map((f) => ({
    id: f.id,
    afinidade: afinidade(f, gosto, pesos),
  }));

  const valores = pontuados.map((p) => p.afinidade);
  const menor = Math.min(...valores);
  const maior = Math.max(...valores);
  const amplitude = maior - menor;

  const comScore = pontuados.map((p) => ({
    id: p.id,
    score: amplitude > 1e-12 ? (p.afinidade - menor) / amplitude : 0,
  }));

  comScore.sort((a, b) => b.score - a.score);
  return comScore.slice(0, limite);
}

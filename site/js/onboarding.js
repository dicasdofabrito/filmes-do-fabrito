// Amostra diversificada para a partida a fria: agrupa candidatos por
// (decada, primeiro genero) e escolhe em rodízio entre os grupos, sempre
// pegando o de maior vote_count restante em cada grupo -- isso espalha a
// amostra em vez de devolver vinte blockbusters americanos seguidos.

function chaveDoGrupo(filme) {
  const decada = filme.y ? Math.floor(filme.y / 10) * 10 : "sem-ano";
  const genero = filme.g[0] ?? "sem-genero";
  return `${decada}:${genero}`;
}

export function amostraOnboarding(filmes, tamanho = 200) {
  const candidatos = [...filmes].sort((a, b) => (b.n || 0) - (a.n || 0));

  const grupos = new Map();
  for (const filme of candidatos) {
    const chave = chaveDoGrupo(filme);
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(filme);
  }

  const chavesGrupos = [...grupos.keys()];
  const resultado = [];
  let indiceGrupo = 0;
  let voltasSemProgresso = 0;

  while (resultado.length < tamanho && voltasSemProgresso < chavesGrupos.length) {
    const chave = chavesGrupos[indiceGrupo % chavesGrupos.length];
    const fila = grupos.get(chave);
    if (fila && fila.length > 0) {
      resultado.push(fila.shift());
      voltasSemProgresso = 0;
    } else {
      voltasSemProgresso++;
    }
    indiceGrupo++;
  }

  return resultado;
}

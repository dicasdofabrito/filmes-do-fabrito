// Roteador por hash. Formatos:
//   #/                        -> home
//   #/grade                   -> grade explorando o catálogo inteiro
//   #/grade/<chave>           -> grade mostrando os ids daquela fileira
//   #/grade?vibe=<texto>      -> grade filtrada pela busca do cabeçalho
//   #/grade?keyword=<id>      -> grade filtrada por uma keyword clicada na ficha
//   #/grade?diretor=<id>      -> grade filtrada por um diretor clicado na ficha
//   #/grade?ator=<id>         -> grade filtrada por um ator/atriz clicado na ficha
//   #/filme/<id>              -> ficha do filme

const PARAMETROS_NUMERICOS_DA_GRADE = ["keyword", "diretor", "ator"];

export function analisarHash(hash) {
  const bruto = hash || "";
  const [semQuery, query] = bruto.split("?");
  const limpo = semQuery.replace(/^#\/?/, "");

  if (!limpo) return { tela: "home" };

  const partes = limpo.split("/").filter(Boolean);

  if (partes[0] === "grade") {
    const rota = { tela: "grade", parametro: partes[1] ?? null };
    if (query) {
      const parametros = new URLSearchParams(query);
      const vibe = parametros.get("vibe");
      if (vibe) rota.vibe = vibe;
      for (const chave of PARAMETROS_NUMERICOS_DA_GRADE) {
        const bruto = parametros.get(chave);
        if (bruto === null) continue;
        const numero = Number(bruto);
        if (!Number.isNaN(numero)) rota[chave] = numero;
      }
    }
    return rota;
  }
  if (partes[0] === "filme" && partes[1]) {
    const id = Number(partes[1]);
    if (!Number.isNaN(id)) return { tela: "ficha", parametro: id };
  }

  return { tela: "home" };
}

export function navegarPara(hash) {
  window.location.hash = hash;
}

export function iniciarRoteador(aoMudarRota) {
  const disparar = () => aoMudarRota(analisarHash(window.location.hash));
  window.addEventListener("hashchange", disparar);
  disparar();
}

// Roteador por hash. Formatos:
//   #/                        -> home
//   #/grade                   -> grade explorando o catálogo inteiro
//   #/grade/<chave>           -> grade mostrando os ids daquela fileira
//   #/grade?vibe=<texto>      -> grade filtrada pela busca do cabeçalho
//   #/filme/<id>              -> ficha do filme

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

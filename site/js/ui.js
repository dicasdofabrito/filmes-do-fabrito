// Renderização da tela home: preenche #lista-fileiras com as fileiras de
// shelves.json, pôster a pôster, na ordem publicada. Módulo de DOM --
// sem teste unitário (ver Global Constraints), verificação é visual.

import { obterFilme } from "./store.js";

const URL_POSTER = "https://image.tmdb.org/t/p/w185";
const URL_POSTER_GRANDE = "https://image.tmdb.org/t/p/w500";

function elementoPoster(id) {
  const filme = obterFilme(id);
  const div = document.createElement("a");
  div.href = `#/filme/${id}`;
  div.className = "poster";
  if (!filme) {
    div.textContent = "?";
    return div;
  }
  const img = document.createElement("img");
  img.src = filme.p ? `${URL_POSTER}${filme.p}` : "";
  img.alt = filme.t;
  img.loading = "lazy";
  div.appendChild(img);
  return div;
}

export function renderizarGrade(filmes, titulo) {
  document.getElementById("grade-titulo").textContent = titulo;

  const container = document.getElementById("grade-posteres");
  container.innerHTML = "";
  for (const filme of filmes) {
    const a = document.createElement("a");
    a.href = `#/filme/${filme.id}`;
    a.className = "poster";
    const img = document.createElement("img");
    img.src = filme.p ? `https://image.tmdb.org/t/p/w185${filme.p}` : "";
    img.alt = filme.t;
    img.loading = "lazy";
    a.appendChild(img);
    container.appendChild(a);
  }
}

export function popularFiltroGenero(generos) {
  const select = document.getElementById("filtro-genero");
  // Preserva a primeira opção ("Gênero", já no HTML) e adiciona o resto.
  for (const [id, nome] of Object.entries(generos).sort((a, b) => a[1].localeCompare(b[1], "pt-BR"))) {
    const opcao = document.createElement("option");
    opcao.value = id;
    opcao.textContent = nome;
    select.appendChild(opcao);
  }
}

export function renderizarFicha(detalhe, nomes) {
  const container = document.getElementById("ficha-conteudo");

  const nomeDiretores = detalhe.d.map((id) => nomes.director[id] || `#${id}`).join(", ");
  const nomeElenco = detalhe.c.map((id) => nomes.cast[id] || `#${id}`).join(", ");
  const chipsKeywords = detalhe.k
    .map((id) => nomes.keyword && nomes.keyword[id])
    .filter(Boolean);

  container.innerHTML = `
    <div class="ficha">
      <img class="ficha-poster" src="${detalhe.p ? URL_POSTER_GRANDE + detalhe.p : ""}" alt="${detalhe.t}" />
      <div class="ficha-info">
        <h2>${detalhe.t} ${detalhe.y ? `(${detalhe.y})` : ""}</h2>
        <p class="ficha-meta">${detalhe.r} min ${nomeDiretores ? "· dirigido por " + nomeDiretores : ""}</p>
        <p class="ficha-sinopse">${detalhe.ov || "Sem sinopse disponível."}</p>
        ${nomeElenco ? `<p class="ficha-elenco"><strong>Elenco:</strong> ${nomeElenco}</p>` : ""}
        ${chipsKeywords.length ? `<div class="ficha-keywords">${chipsKeywords.map((k) => `<span class="chip">${k}</span>`).join("")}</div>` : ""}
        <div class="ficha-acoes" id="ficha-acoes"></div>
        <div id="ficha-similares"></div>
      </div>
    </div>
  `;
}

export function renderizarSimilares(pares) {
  const container = document.getElementById("ficha-similares");
  if (pares.length === 0) {
    container.innerHTML = "<p>Sem sugestões parecidas no momento.</p>";
    return;
  }
  const linha = document.createElement("div");
  linha.className = "fileira-linha";
  for (const { id } of pares) {
    linha.appendChild(elementoPoster(id));
  }
  container.innerHTML = "<h3>Se você gostou desse</h3>";
  container.appendChild(linha);
}

export function renderizarHome(fileiras) {
  const container = document.getElementById("lista-fileiras");
  container.innerHTML = "";

  for (const fileira of fileiras) {
    const secao = document.createElement("section");
    secao.className = "fileira";

    const titulo = document.createElement("a");
    titulo.href = `#/grade/${fileira.key}`;
    titulo.className = "fileira-titulo";
    titulo.textContent = fileira.title;
    secao.appendChild(titulo);

    const linha = document.createElement("div");
    linha.className = "fileira-linha";
    for (const id of fileira.ids) {
      linha.appendChild(elementoPoster(id));
    }
    secao.appendChild(linha);

    container.appendChild(secao);
  }
}
